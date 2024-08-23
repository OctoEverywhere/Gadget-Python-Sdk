import time
import threading
from typing import Callable


import requests


class GadgetInspectionSession:

    # Well known SDK Error Types
    # These Error Type or the Error Types defined in the API documentation can be fired by the SDK.
    ErrorTypeInternal = "OE_SDK_ERROR"
    ErrorTypeCallbackFailure = "OE_SDK_CALLBACK_EXCEPTION"


    def __init__(
        self,
        apiKey: str,
        minProcessingIntervalSec:int = 0,
        on_new_image_request:  Callable[[None], bytes] = None,
        on_state_update:       Callable[[int, bool, bool], None] = None,
        on_error:              Callable[[str, str], None] = None
    ) -> None:
        """
        GadgetInspectionSession Initialization

        Parameters
        ----------
        apiKey: str
            Your OctoEverywhere API key.

        minProcessingIntervalSec: int (default 0)
            This is the min interval between processing API requests.
            If the value is 0 (default), we will call the API at the dynamic interval requested by the API after each request.
            If the value is set to a positive number, we will use which ever is larger, the dynamic interval from the API or the value set here.

        on_new_image_request: function () -> bytes
            Callback for when a new image needs to be processed for print failure detection. This function should return the image data or None if no image is available.

        on_state_update: function(score:int, warningSuggested:bool, pauseSuggested:bool) -> None
            Callback after an image process when there's a new model state.
            score:int - A value between 0 and 100, 0 is a perfect print and 100 being a very strong likely hood of failure.
            warningSuggested:bool - Set to True if the OctoEverywhere temporal combination algorithm suggests a warning should be fired.
            pauseSuggested:bool   - Set to True if the OctoEverywhere temporal combination algorithm suggests the print should be paused due to failure.

        on_error: function(errorType:str, errorDetails:str) -> None
            Callback for when an error occurs.
            errorType:str    - One of the well known errors as described in the API documentation.
            errorDetails:str - A string with more information about the error.
        """
        self.apiKey = apiKey
        self.on_new_image_request = on_new_image_request
        self.on_state_update = on_state_update
        self.on_error = on_error
        self.minProcessingIntervalSec = minProcessingIntervalSec
        self.thread:threading.Thread = None
        self.threadLock = threading.Lock()
        self.hasRan = False
        self.isRunning = False
        self.UseFallbackUrl = False

        # Ensure the required values are set.
        if self.apiKey is None or len(self.apiKey) == 0:
            raise Exception("API Key must be provided.")
        if self.on_new_image_request is None:
            raise Exception("on_new_image_request must be provided.")
        if self.on_state_update is None:
            raise Exception("on_state_update must be provided.")
        if self.minProcessingIntervalSec < 0:
            raise Exception("minProcessingIntervalSec must be a positive number or zero.")

        # Session Context Information
        # This is the ID of this context we use to identify the session.
        self.ContextId:str = None
        # This is returned when we create the context, it's the main URL we should use to make processing requests.
        self.ProcessRequestUrl:str = None
        # This is returned when we create the context, it's the URL we should try as a fallback if our main processing requests URL fails.
        self.ProcessRequestFallbackUrl:str = None

        # This is the min amount of time we must sleep as requested from the process API
        self.SleepIntervalSec = 60



    def start(self) -> None:
        """
        Start the inspection session.
        """
        with self.threadLock:
            if self.hasRan is True:
                raise Exception("The Gadget session has already been started, each session can only be used once.")
            self.hasRan = True
            self.isRunning = True
            self.thread = threading.Thread(target=self._threadWorker)
            self.thread.start()


    def stop(self) -> None:
        """
        Stop the inspection session.
        """
        with self.threadLock:
            if self.thread is not None:
                self.isRunning = False
                self.thread.join()
                self.thread = None


    def _threadWorker(self) -> None:
        # Once we are running, we will keep running until the session is stopped.
        while self.isRunning:
            try:
                # Ensure we have a context.
                if not self._ensureSessionContext():
                    # If we failed to create a context, we will sleep for a bit and try again.
                    time.sleep(30)
                    continue

                # If we have a context, we can now process a new image.
                imageBytes = None
                try:
                    imageBytes = self.on_new_image_request()
                except Exception as e:
                    self._fireOnError(GadgetInspectionSession.ErrorTypeCallbackFailure, str(e))

                # If the client returns none we skip this processing.
                if imageBytes is not None:
                    self._processImage(imageBytes)

                # Sleep the next processing time interval.
                time.sleep(self.SleepIntervalSec)

            except Exception as e:
                self._fireOnError(GadgetInspectionSession.ErrorTypeInternal, str(e))
                time.sleep(self.SleepIntervalSec)


    # Ensures there's a session context, if not, one is created.
    # Returns True on success, False on failure and will call the error handler.
    def _ensureSessionContext(self) -> bool:
        # If we already have a context, we're good.
        if self.ContextId is not None:
            return True

        try:
            # If there's no context, create one now.
            response = requests.post(
                self._buildUrl("/api/gadget/v1/createcontext"),
                headers={
                    "X-API-Key": self.apiKey
                },
                timeout = 30
            )

            # Check for a valid response.
            if response.status_code != 200:
                # If the API failed, see if we can parse the error.
                errorType, errorDetails = self._tryParseApiErrorResponse(response)
                if errorType is not None and errorDetails is not None:
                    self._fireOnError(errorType, errorDetails)
                    return False
                raise Exception("Failed to create a new session context: " + response.text)

            # Parse the response.
            # Grab the data we need.
            responseJson = response.json()
            self.ContextId = responseJson.get("ContextId", None)
            self.ProcessRequestUrl = responseJson.get("ProcessRequestUrl", None)
            self.ProcessRequestFallbackUrl = responseJson.get("FallbackProcessRequestUrl", None)

            # Validate the data we got.
            if self.ContextId is None:
                raise Exception("Failed to get a valid context ID from the response.")
            if self.ProcessRequestUrl is None:
                raise Exception("Failed to get a valid ProcessRequestUrl from the response.")
            if self.ProcessRequestFallbackUrl is None:
                raise Exception("Failed to get a valid FallbackProcessRequestUrl from the response.")

            # Context created!
            return True

        except Exception as e:
            self._fireOnError(GadgetInspectionSession.ErrorTypeInternal, str(e))
        return False


    # Calls the image process API and handles firing the resulting callbacks.
    def _processImage(self, imageBytes) -> None:
        try:
            # Use the main process request URl unless it has failed and we are using the fallback.
            # Note once we switch to the fallback URL, we will use it for the rest of the session.
            requestUrl = self.ProcessRequestUrl if not self.UseFallbackUrl else self.ProcessRequestFallbackUrl

            # Create the image payload request, the image must be sent as a multipart form file attachment, called "snapshot".
            files = {}
            files['attachment'] = ("snapshot", imageBytes)

            # Make the image process request.
            # We use a long timeout to allow the server a good amount of time for the processing.
            response = requests.post(
                requestUrl,
                files=files,
                headers={
                    "X-API-Key": self.apiKey
                },
                timeout = 2 * 60
            )

            # Check for a valid response.
            if response.status_code != 200:
                # If the API failed, see if we can parse the error.
                errorType, errorDetails = self._tryParseApiErrorResponse(response)
                if errorType is not None and errorDetails is not None:
                    # If we fail for any reason, switch to the fallback URL.
                    self.UseFallbackUrl = True
                    self._fireOnError(errorType, errorDetails)
                    return
                raise Exception("Failed to call process api: " + response.text)

            # Parse the response.
            # Grab the data we need.
            responseJson = response.json()
            nextProcessIntervalSec = responseJson.get("NextProcessIntervalSec", None)
            score = responseJson.get("Score", None)
            warningSuggested = responseJson.get("WarningSuggested", None)
            pauseSuggested = responseJson.get("PauseSuggested", None)

            # Set the next processing interval.
            if nextProcessIntervalSec is None:
                raise Exception("Failed to get a valid NextProcessIntervalSec from process API response.")
            self.SleepIntervalSec = max(nextProcessIntervalSec, self.minProcessingIntervalSec)
            self._sanityCheckProcessingInterval()

            # Validate the results
            if score is None:
                raise Exception("Failed to get a valid Score from process API response.")
            if warningSuggested is None:
                raise Exception("Failed to get a valid WarningSuggested from process API response.")
            if pauseSuggested is None:
                raise Exception("Failed to get a valid PauseSuggested from process API response.")

            # Fire the state update callback.
            try:
                self.on_state_update(score, warningSuggested, pauseSuggested)
            except Exception as e:
                self._fireOnError(GadgetInspectionSession.ErrorTypeCallbackFailure, str(e))

        except Exception as e:
            # If we fail for any reason, switch to the fallback URL.
            self.UseFallbackUrl = True
            self._fireOnError(GadgetInspectionSession.ErrorTypeInternal, str(e))


    def _sanityCheckProcessingInterval(self) -> None:
        # A helper function to ensure the processing interval is within a reasonable range.
        self.SleepIntervalSec = max(20, self.SleepIntervalSec)
        self.SleepIntervalSec = min(3600, self.SleepIntervalSec)


    def _buildUrl(self, suffix) -> str:
        # A helper function to help local debugging.
        localServerDebugAddress = None
        if localServerDebugAddress is not None:
            return "http://" + localServerDebugAddress + suffix
        return "https://gadget-pv1-oeapi.octoeverywhere.com" + suffix


    def _tryParseApiErrorResponse(self, response: requests.Response):
        # Given a http response, this will try to parse the wellknown error type out if possible.
        try:
            json = response.json()
            errorType = json.get("ErrorType", None)
            errorDetails = json.get("ErrorDetails", None)
            if errorType is not None and errorDetails is not None:
                return (errorType, errorDetails)
        except Exception:
            pass
        return (None, None)


    def _fireOnError(self, errorType:str, errorDetails: str) -> None:
        # A helper to fire the error callback.
        if self.on_error is not None:
            try:
                self.on_error(errorType, errorDetails)
            except Exception as e:
                print(f"Error in error handler: {str(e)}")
