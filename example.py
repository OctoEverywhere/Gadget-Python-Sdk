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
        self.gadgetSession:GadgetInspectionSession = None


    def Run(self):

        # Create the new session given your API key and the required callbacks.
        # Each session can only be used to track a single print, as the context creates a context that is used to track the print.
        # When a new print begins, a new session should be created.
        self.gadgetSession = GadgetInspectionSession(
            Example.ApiKey,
            on_new_image_request=self.OnNewImageRequest,
            on_state_update=self.OnStateUpdate,
            on_error=self.OnError
        )

        # Start the session to run async.
        self.gadgetSession.start()

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
        #
        # score:int - This is the temporal combination model print quality score.
        #             The score ranges from 0-100. 0 indicates a perfect print and 100 indicates a strong probability of a failure.
        #             You can use this score directly to indicate the current print quality to the user.
        # warningSuggested:bool - Set to true if the temporal combination model is confident there might be a print issue and the user should be informed.
        #                         This decision is based on many signals and is only sent when there's high confidence of the warning state.
        # pauseSuggested:bool   - Set to true if the temporal combination model is confident that there is probably a print failure and that the print should be paused.
        #                         This decision is based on many signals and is only sent when there's high confidence that the print has failed.
        #
        print(f"Image processing complete. New State - Score: {score}, Warning: {warningSuggested}, Pause: {pauseSuggested}")

        # Here's an example how how you might want to update the state of print on a UI the user can see.
        if score >= 99:
            print("Print Status: Issue Detected")
        elif score >= 97:
            print("Print Status: There's Probably An Issue")
        elif score >= 95:
            print("Print Status: There Might An Issue")
        elif score >= 80:
            print("Print Status: Possible Issue")
        elif score >= 60:
            print("Print Status: Monitoring A Possible Issue")
        elif score >= 30:
            print("Print Status: Looking Good")
        else:
            print("Print Status: Looking Great")

        # If a warning is suggested, you can inform the user on the UI or by sending them a message.
        if warningSuggested:
            print("Hey! You're print might be failing. Go take a look!")

        # If a pause is suggested you can pause the print.
        # If you do pause the print, you should call the pause method on the session, since there's no need to keep calling the API when the print is paused.
        # If the print is resumed, you can decided if you want to resume the session to continue monitoring or stop monitoring this print.
        if pauseSuggested:
            print("Print pause suggested. Pausing the print...")
            self.gadgetSession.pause()


    def OnError(self, errorType: str, errorDetails: str) -> None:
        # Called when an error occurs.
        # errorType:str    - One of the well known errors as described in the API documentation.
        # errorDetails:str - A string with more information about the error.
        # Details: https://octoeverywhere.stoplight.io/docs/octoeverywhere-api-docs/3xadck728cc0t-ai-failure-detection-ap-is#errors
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
