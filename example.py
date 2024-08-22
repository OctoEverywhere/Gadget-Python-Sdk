import os
import time

from gadgetsdk import GadgetInspectionSession

#
# An example of how to use the OctoEverywhere Gadget SDK for AI 3D Printing Failure Detection.
#
# Read the API docs for full details:
# https://octoeverywhere.stoplight.io/docs/octoeverywhere-api-docs/3xadck728cc0t-octo-everywhere-ai-failure-detection-api
#

class Example:

    # Using this example constant we can control how long after starting the session we start returning an image of a failed print.
    PrintFailureTimeStartSec = 2 * 60

    # Your OctoEverywhere API key.
    # See the OctoEverywhere developer page or contact support to get your API key.
    ApiKey = ""


    def __init__(self):
        self._startTimeSec = time.time()


    def Run(self):

        # Create the new session given your API key and the required callbacks.
        # Each session can only be used to track a single print, as the context creates a context that is used to track the print.
        # When a new print begins, a new session should be created.
        session = GadgetInspectionSession(
            Example.ApiKey,
            on_new_image_request=self.OnNewImageRequest,
            on_state_update=self.OnStateUpdate,
            on_error=self.OnError
        )

        # Start the session to run async.
        session.start()

        # Normally your program would return and do whatever else it wants to do, but in this case,
        # we will just sleep to block the main thread.
        time.sleep(50000)


    def OnNewImageRequest(self) -> bytes:
        # This function is called when a new webcam snapshot needs to be retrieved for processing.
        # The image type must be a jpeg image, and the bytes array should contain the image data including the jpeg image headers.
        # If the image can't be gotten or there's a failure, it should return None.

        # For this example, we will use two static images, one that's a good print and the other that's a failed print.
        if time.time() - self._startTimeSec > self.PrintFailureTimeStartSec:
            return self._getImage(False)
        return self._getImage(True)


    def OnStateUpdate(self, score:int, warningSuggested:bool, pauseSuggested:bool) -> None:
        # Called after an image process when there's a new model state.
        # score:int - A value between 0 and 100, 0 is a perfect print and 100 being a very strong likely hood of failure.
        # warningSuggested:bool - Set to True if the OctoEverywhere temporal combination algorithm suggests a warning should be fired.
        # pauseSuggested:bool   - Set to True if the OctoEverywhere temporal combination algorithm suggests the print should be paused due to failure.
        print(f"Image processing complete. New State - Score: {score}, Warning: {warningSuggested}, Pause: {pauseSuggested}")


    def OnError(self, errorType: str, errorDetails: str) -> None:
        # Called when an error occurs.
        # errorType:str    - One of the well known errors as described in the API documentation.
        # errorDetails:str - A string with more information about the error.
        # Details: https://octoeverywhere.stoplight.io/docs/octoeverywhere-api-docs/3xadck728cc0t-octo-everywhere-ai-failure-detection-api
        print(f"Error: {errorType} - {errorDetails}")


    def _getImage(self, goodPrint: bool) -> bytes:
        # A helper function to get the image data from the sample images.
        scriptFilePath = os.path.realpath(__file__)
        scriptDir = os.path.dirname(scriptFilePath)
        fileName = "sample-good-print.jpg" if goodPrint else "sample-failed-print.jpg"
        with open(os.path.join(scriptDir, "sample-images", fileName), "rb") as f:
            return f.read()


if __name__ == "__main__":
    e = Example()
    e.Run()
