import json
import ssl
import sys
import threading
import time
import warnings
from datetime import datetime
from queue import Queue

import keyring
import websocket
from pydispatch import Dispatcher

# -----------------------------------------------------------
#
# GETTING STARTED
#   - Please reference to https://emotiv.gitbook.io/cortex-api/ first.
#   - Connect your headset with dongle or bluetooth. You can see the headset via Emotiv Launcher
#   - Please make sure the your_app_client_id and your_app_client_secret are set before starting running.
#   - In the case you borrow license from others, you need to add license = "xxx-yyy-zzz" as init parameter
# RESULT
#   - the data labels will be retrieved at on_new_data_labels
#   - the data will be retreived at on_new_[dataStream]_data
#
# -----------------------------------------------------------


def main(key="basic", url="ws://localhost:8000/connect/text", debug=False):
    # Please fill your application clientId and clientSecret before running script
    your_app_client_id = keyring.get_password("emotiv.com", key)
    your_app_client_secret = keyring.get_password("emotiv.com", your_app_client_id)

    queue = Queue()

    q = QueryAPI(url, queue, debug)

    q.open()

    s = Subcribe(your_app_client_id, your_app_client_secret, queue, debug)

    # list data streams
    streams = ["eeg", "mot", "met", "pow"]
    s.start(streams)
    try:
        while True:
            input("Press Enter to generate AI...")
            result = q.trigger()
            print(result)
    except KeyboardInterrupt:
        q.close()
        s.close()


class Subcribe:
    """
    A class to subscribe data stream.

    Attributes
    ----------
    c : Cortex
        Cortex communicate with Emotiv Cortex Service

    Methods
    -------
    start():
        start data subscribing process.
    sub(streams):
        To subscribe to one or more data streams.
    on_new_data_labels(*args, **kwargs):
        To handle data labels of subscribed data
    on_new_eeg_data(*args, **kwargs):
        To handle eeg data emitted from Cortex
    on_new_mot_data(*args, **kwargs):
        To handle motion data emitted from Cortex
    on_new_dev_data(*args, **kwargs):
        To handle device information data emitted from Cortex
    on_new_met_data(*args, **kwargs):
        To handle performance metrics data emitted from Cortex
    on_new_pow_data(*args, **kwargs):
        To handle band power data emitted from Cortex
    """

    def __init__(self, app_client_id, app_client_secret, queue, debug=True, **kwargs):
        """
        Constructs cortex client and bind a function to handle subscribed data streams
        If you do not want to log request and response message , set debug_mode = False. The default is True
        """
        print("Subscribe __init__")
        self.c = Cortex(app_client_id, app_client_secret, debug_mode=debug, **kwargs)
        self.c.bind(create_session_done=self.on_create_session_done)
        self.c.bind(new_data_labels=self.on_new_data_labels)
        self.c.bind(new_eeg_data=self.on_new_eeg_data)
        self.c.bind(new_mot_data=self.on_new_mot_data)
        self.c.bind(new_dev_data=self.on_new_dev_data)
        self.c.bind(new_met_data=self.on_new_met_data)
        self.c.bind(new_pow_data=self.on_new_pow_data)
        self.c.bind(inform_error=self.on_inform_error)
        self.queue = queue
        self.debug = debug
        self.labels = {}

    def start(self, streams, headsetId=""):
        """
        To start data subscribing process as below workflow
        (1)check access right -> authorize -> connect headset->create session
        (2) subscribe streams data
        'eeg': EEG
        'mot' : Motion
        'dev' : Device information
        'met' : Performance metric
        'pow' : Band power
        'eq' : EEQ Quality

        Parameters
        ----------
        streams : list, required
            list of streams. For example, ['eeg', 'mot']
        headsetId: string , optional
             id of wanted headet which you want to work with it.
             If the headsetId is empty, the first headset in list will be set as wanted headset
        Returns
        -------
        None
        """
        self.streams = streams

        if headsetId != "":
            self.c.set_wanted_headset(headsetId)

        self.c.open()

    def sub(self, streams):
        """
        To subscribe to one or more data streams
        'eeg': EEG
        'mot' : Motion
        'dev' : Device information
        'met' : Performance metric
        'pow' : Band power

        Parameters
        ----------
        streams : list, required
            list of streams. For example, ['eeg', 'mot']

        Returns
        -------
        None
        """
        self.c.sub_request(streams)

    def unsub(self, streams):
        """
        To unsubscribe to one or more data streams
        'eeg': EEG
        'mot' : Motion
        'dev' : Device information
        'met' : Performance metric
        'pow' : Band power

        Parameters
        ----------
        streams : list, required
            list of streams. For example, ['eeg', 'mot']

        Returns
        -------
        None
        """
        self.c.unsub_request(streams)

    def print(self, *args, **kwargs):
        if self.debug:
            print(*args, **kwargs)

    def on_new_data_labels(self, *args, **kwargs):
        """
        To handle data labels of subscribed data
        Returns
        -------
        data: list
              array of data labels
        name: stream name
        For example:
            eeg: ["COUNTER","INTERPOLATED", "AF3", "T7", "Pz", "T8", "AF4", "RAW_CQ", "MARKER_HARDWARE"]
            motion: ['COUNTER_MEMS', 'INTERPOLATED_MEMS', 'Q0', 'Q1', 'Q2', 'Q3', 'ACCX', 'ACCY', 'ACCZ', 'MAGX', 'MAGY', 'MAGZ']
            dev: ['AF3', 'T7', 'Pz', 'T8', 'AF4', 'OVERALL']
            met : ['eng.isActive', 'eng', 'exc.isActive', 'exc', 'lex', 'str.isActive', 'str', 'rel.isActive', 'rel', 'int.isActive', 'int', 'foc.isActive', 'foc']
            pow: ['AF3/theta', 'AF3/alpha', 'AF3/betaL', 'AF3/betaH', 'AF3/gamma', 'T7/theta', 'T7/alpha', 'T7/betaL', 'T7/betaH', 'T7/gamma', 'Pz/theta', 'Pz/alpha', 'Pz/betaL', 'Pz/betaH', 'Pz/gamma', 'T8/theta', 'T8/alpha', 'T8/betaL', 'T8/betaH', 'T8/gamma', 'AF4/theta', 'AF4/alpha', 'AF4/betaL', 'AF4/betaH', 'AF4/gamma']
        """
        data = kwargs.get("data")
        stream_name = data["streamName"]
        stream_labels = data["labels"]
        self.labels[stream_name] = stream_labels
        self.print("{} labels are : {}".format(stream_name, stream_labels))

    def on_new_data(self, key, data, data_key=None):
        data[key] = dict(zip(self.labels[key], data[data_key or key]))
        self.queue.put(data)

    def on_new_eeg_data(self, *args, **kwargs):
        """
        To handle eeg data emitted from Cortex

        Returns
        -------
        data: dictionary
             The values in the array eeg match the labels in the array labels return at on_new_data_labels
        For example:
           {'eeg': [99, 0, 4291.795, 4371.795, 4078.461, 4036.41, 4231.795, 0.0, 0], 'time': 1627457774.5166}
        """

        data = kwargs.get("data")
        self.on_new_data("eeg", data)
        self.print("eeg data: {}".format(data))

    def on_new_mot_data(self, *args, **kwargs):
        """
        To handle motion data emitted from Cortex

        Returns
        -------
        data: dictionary
             The values in the array motion match the labels in the array labels return at on_new_data_labels
        For example: {'mot': [33, 0, 0.493859, 0.40625, 0.46875, -0.609375, 0.968765, 0.187503, -0.250004, -76.563667, -19.584995, 38.281834], 'time': 1627457508.2588}
        """
        data = kwargs.get("data")
        self.on_new_data("mot", data)
        self.print("motion data: {}".format(data))

    def on_new_dev_data(self, *args, **kwargs):
        """
        To handle dev data emitted from Cortex

        Returns
        -------
        data: dictionary
             The values in the array dev match the labels in the array labels return at on_new_data_labels
        For example:  {'signal': 1.0, 'dev': [4, 4, 4, 4, 4, 100], 'batteryPercent': 80, 'time': 1627459265.4463}
        """
        data = kwargs.get("data")
        self.on_new_data("dev", data)
        self.print("dev data: {}".format(data))

    def on_new_met_data(self, *args, **kwargs):
        """
        To handle performance metrics data emitted from Cortex

        Returns
        -------
        data: dictionary
             The values in the array met match the labels in the array labels return at on_new_data_labels
        For example: {'met': [True, 0.5, True, 0.5, 0.0, True, 0.5, True, 0.5, True, 0.5, True, 0.5], 'time': 1627459390.4229}
        """
        data = kwargs.get("data")
        self.on_new_data("met", data)
        self.print("pm data: {}".format(data))

    def on_new_pow_data(self, *args, **kwargs):
        """
        To handle band power data emitted from Cortex

        Returns
        -------
        data: dictionary
             The values in the array pow match the labels in the array labels return at on_new_data_labels
        For example: {'pow': [5.251, 4.691, 3.195, 1.193, 0.282, 0.636, 0.929, 0.833, 0.347, 0.337, 7.863, 3.122, 2.243, 0.787, 0.496, 5.723, 2.87, 3.099, 0.91, 0.516, 5.783, 4.818, 2.393, 1.278, 0.213], 'time': 1627459390.1729}
        """
        data = kwargs.get("data")
        self.on_new_data("pow", data)
        self.print("pow data: {}".format(data))

    # callbacks functions
    def on_create_session_done(self, *args, **kwargs):
        print("on_create_session_done")

        # subribe data
        self.sub(self.streams)

    def on_inform_error(self, *args, **kwargs):
        error_data = kwargs.get("error_data")
        print(error_data)


# -----------------------------------------------------------

# define request id
QUERY_HEADSET_ID = 1
CONNECT_HEADSET_ID = 2
REQUEST_ACCESS_ID = 3
AUTHORIZE_ID = 4
CREATE_SESSION_ID = 5
SUB_REQUEST_ID = 6
SETUP_PROFILE_ID = 7
QUERY_PROFILE_ID = 8
TRAINING_ID = 9
DISCONNECT_HEADSET_ID = 10
CREATE_RECORD_REQUEST_ID = 11
STOP_RECORD_REQUEST_ID = 12
EXPORT_RECORD_ID = 13
INJECT_MARKER_REQUEST_ID = 14
SENSITIVITY_REQUEST_ID = 15
MENTAL_COMMAND_ACTIVE_ACTION_ID = 16
MENTAL_COMMAND_BRAIN_MAP_ID = 17
MENTAL_COMMAND_TRAINING_THRESHOLD = 18
SET_MENTAL_COMMAND_ACTIVE_ACTION_ID = 19
HAS_ACCESS_RIGHT_ID = 20
GET_CURRENT_PROFILE_ID = 21
GET_CORTEX_INFO_ID = 22
UPDATE_MARKER_REQUEST_ID = 23
UNSUB_REQUEST_ID = 24

# define error_code
ERR_PROFILE_ACCESS_DENIED = -32046

# define warning code
CORTEX_STOP_ALL_STREAMS = 0
CORTEX_CLOSE_SESSION = 1
USER_LOGIN = 2
USER_LOGOUT = 3
ACCESS_RIGHT_GRANTED = 9
ACCESS_RIGHT_REJECTED = 10
PROFILE_LOADED = 13
PROFILE_UNLOADED = 14
CORTEX_AUTO_UNLOAD_PROFILE = 15
EULA_ACCEPTED = 17
DISKSPACE_LOW = 19
DISKSPACE_CRITICAL = 20
HEADSET_CANNOT_CONNECT_TIMEOUT = 102
HEADSET_DISCONNECTED_TIMEOUT = 103
HEADSET_CONNECTED = 104
HEADSET_CANNOT_WORK_WITH_BTLE = 112
HEADSET_CANNOT_CONNECT_DISABLE_MOTION = 113


class Cortex(Dispatcher):
    _events_ = [
        "inform_error",
        "create_session_done",
        "query_profile_done",
        "load_unload_profile_done",
        "save_profile_done",
        "get_mc_active_action_done",
        "mc_brainmap_done",
        "mc_action_sensitivity_done",
        "mc_training_threshold_done",
        "create_record_done",
        "stop_record_done",
        "warn_cortex_stop_all_sub",
        "inject_marker_done",
        "update_marker_done",
        "export_record_done",
        "new_data_labels",
        "new_com_data",
        "new_fe_data",
        "new_eeg_data",
        "new_mot_data",
        "new_dev_data",
        "new_met_data",
        "new_pow_data",
        "new_sys_data",
    ]

    def __init__(self, client_id, client_secret, debug_mode=False, **kwargs):
        self.session_id = ""
        self.headset_id = ""
        self.debug = debug_mode
        self.debit = 10
        self.license = ""

        if client_id == "":
            raise ValueError(
                "Empty your_app_client_id. Please fill in your_app_client_id before running the example."
            )
        else:
            self.client_id = client_id

        if client_secret == "":
            raise ValueError(
                "Empty your_app_client_secret. Please fill in your_app_client_secret before running the example."
            )
        else:
            self.client_secret = client_secret

        for key, value in kwargs.items():
            print("init {0} - {1}".format(key, value))
            if key == "license":
                self.license = value
            elif key == "debit":
                self.debit == value
            elif key == "headset_id":
                self.headset_id = value

    def open(self):
        url = "wss://localhost:6868"
        # websocket.enableTrace(True)
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_open=self.on_open,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        threadName = "WebsockThread:-{:%Y%m%d%H%M%S}".format(datetime.utcnow())

        # As default, a Emotiv self-signed certificate is required.
        # If you don't want to use the certificate, please replace by the below line  by sslopt={"cert_reqs": ssl.CERT_NONE}
        sslopt = {
            "ca_certs": "./rootCA.pem",
            "cert_reqs": ssl.CERT_REQUIRED,
        }

        self.websock_thread = threading.Thread(
            target=self.ws.run_forever, args=(None, sslopt), name=threadName
        )
        self.websock_thread.start()

    def join(self):
        self.websock_thread.join()

    def close(self):
        self.ws.close()

    def set_wanted_headset(self, headsetId):
        self.headset_id = headsetId

    def set_wanted_profile(self, profileName):
        self.profile_name = profileName

    def on_open(self, *args, **kwargs):
        print("websocket opened")
        self.do_prepare_steps()

    def on_error(self, *args):
        if len(args) == 2:
            print(str(args[1]))

    def on_close(self, *args, **kwargs):
        print("on_close")
        print(args[1])

    def handle_result(self, recv_dic):
        if self.debug:
            print(recv_dic)

        req_id = recv_dic["id"]
        result_dic = recv_dic["result"]

        if req_id == HAS_ACCESS_RIGHT_ID:
            self.handle_has_access_right_id(result_dic)
        elif req_id == REQUEST_ACCESS_ID:
            self.handle_request_access_id(result_dic)
        elif req_id == AUTHORIZE_ID:
            self.handle_authorize_id(result_dic)
        elif req_id == QUERY_HEADSET_ID:
            self.handle_query_headset_id(result_dic)
        elif req_id == CREATE_SESSION_ID:
            self.handle_create_session_id(result_dic)
        elif req_id == SUB_REQUEST_ID:
            self.handle_sub_request_id(result_dic)
        elif req_id == UNSUB_REQUEST_ID:
            self.handle_unsub_request_id(result_dic)
        elif req_id == QUERY_PROFILE_ID:
            self.handle_query_profile_id(result_dic)
        elif req_id == SETUP_PROFILE_ID:
            self.handle_setup_profile_id(result_dic)
        elif req_id == GET_CURRENT_PROFILE_ID:
            self.handle_get_current_profile_id(result_dic)
        elif req_id == DISCONNECT_HEADSET_ID:
            self.handle_disconnect_headset_id(result_dic)
        elif req_id == MENTAL_COMMAND_ACTIVE_ACTION_ID:
            self.handle_mental_command_active_action_id(result_dic)
        elif req_id == MENTAL_COMMAND_TRAINING_THRESHOLD:
            self.handle_mental_command_training_threshold(result_dic)
        elif req_id == MENTAL_COMMAND_BRAIN_MAP_ID:
            self.handle_mental_command_brain_map_id(result_dic)
        elif req_id == SENSITIVITY_REQUEST_ID:
            self.handle_sensitivity_request_id(result_dic)
        elif req_id == CREATE_RECORD_REQUEST_ID:
            self.handle_create_record_request_id(result_dic)
        elif req_id == STOP_RECORD_REQUEST_ID:
            self.handle_stop_record_request_id(result_dic)
        elif req_id == EXPORT_RECORD_ID:
            self.handle_export_record_id(result_dic)
        elif req_id == INJECT_MARKER_REQUEST_ID:
            self.handle_inject_marker_request_id(result_dic)
        elif req_id == UPDATE_MARKER_REQUEST_ID:
            self.handle_update_marker_request_id(result_dic)
        else:
            print("No handling for response of request " + str(req_id))

    def handle_has_access_right_id(self, result_dic):
        access_granted = result_dic["accessGranted"]
        if access_granted is True:
            # authorize
            self.authorize()
        else:
            # request access
            self.request_access()

    def handle_request_access_id(self, result_dic):
        access_granted = result_dic["accessGranted"]

        if access_granted is True:
            # authorize
            self.authorize()
        else:
            # wait approve from Emotiv Launcher
            msg = result_dic["message"]
            warnings.warn(msg)

    def handle_authorize_id(self, result_dic):
        print("Authorize successfully.")
        self.auth = result_dic["cortexToken"]
        # query headsets
        self.query_headset()

    def handle_query_headset_id(self, result_dic):
        self.headset_list = result_dic
        found_headset = False
        headset_status = ""
        for ele in self.headset_list:
            hs_id = ele["id"]
            status = ele["status"]
            connected_by = ele["connectedBy"]
            print(
                "headsetId: {0}, status: {1}, connected_by: {2}".format(
                    hs_id, status, connected_by
                )
            )
            if self.headset_id != "" and self.headset_id == hs_id:
                found_headset = True
                headset_status = status

        if len(self.headset_list) == 0:
            warnings.warn("No headset available. Please turn on a headset.")
        elif self.headset_id == "":
            # set first headset is default headset
            self.headset_id = self.headset_list[0]["id"]
            # call query headet again
            self.query_headset()
        elif found_headset is False:
            warnings.warn(
                "Can not found the headset "
                + self.headset_id
                + ". Please make sure the id is correct."
            )
        elif found_headset is True:
            if headset_status == "connected":
                # create session with the headset
                self.create_session()
            elif headset_status == "discovered":
                self.connect_headset(self.headset_id)
            elif headset_status == "connecting":
                # wait 3 seconds and query headset again
                time.sleep(3)
                self.query_headset()
            else:
                warnings.warn(
                    "query_headset resp: Invalid connection status " + headset_status
                )

    def handle_create_session_id(self, result_dic):
        self.session_id = result_dic["id"]
        print("The session " + self.session_id + " is created successfully.")
        self.emit("create_session_done", data=self.session_id)

    def handle_sub_request_id(self, result_dic):
        # handle data label
        for stream in result_dic["success"]:
            stream_name = stream["streamName"]
            stream_labels = stream["cols"]
            print("The data stream " + stream_name + " is subscribed successfully.")
            # ignore com, fac and sys data label because they are handled in on_new_data
            if stream_name != "com" and stream_name != "fac":
                self.extract_data_labels(stream_name, stream_labels)

        for stream in result_dic["failure"]:
            stream_name = stream["streamName"]
            stream_msg = stream["message"]
            print(
                "The data stream "
                + stream_name
                + " is subscribed unsuccessfully. Because: "
                + stream_msg
            )

    def handle_unsub_request_id(self, result_dic):
        for stream in result_dic["success"]:
            stream_name = stream["streamName"]
            print("The data stream " + stream_name + " is unsubscribed successfully.")

        for stream in result_dic["failure"]:
            stream_name = stream["streamName"]
            stream_msg = stream["message"]
            print(
                "The data stream "
                + stream_name
                + " is unsubscribed unsuccessfully. Because: "
                + stream_msg
            )

    def handle_query_profile_id(self, result_dic):
        profile_list = []
        for ele in result_dic:
            name = ele["name"]
            profile_list.append(name)
        self.emit("query_profile_done", data=profile_list)

    def handle_setup_profile_id(self, result_dic):
        action = result_dic["action"]
        if action == "create":
            profile_name = result_dic["name"]
            if profile_name == self.profile_name:
                # load profile
                self.setup_profile(profile_name, "load")
        elif action == "load":
            print("load profile successfully")
            self.emit("load_unload_profile_done", isLoaded=True)
        elif action == "unload":
            self.emit("load_unload_profile_done", isLoaded=False)
        elif action == "save":
            self.emit("save_profile_done")

    def handle_get_current_profile_id(self, result_dic):
        print(result_dic)
        name = result_dic["name"]
        if name is None:
            # no profile loaded with the headset
            print(
                "get_current_profile: no profile loaded with the headset "
                + self.headset_id
            )
            self.setup_profile(self.profile_name, "load")
        else:
            loaded_by_this_app = result_dic["loadedByThisApp"]
            print(
                "get current profile rsp: "
                + name
                + ", loadedByThisApp: "
                + str(loaded_by_this_app)
            )
            if name != self.profile_name:
                warnings.warn(
                    "There is profile "
                    + name
                    + " is loaded for headset "
                    + self.headset_id
                )
            elif loaded_by_this_app is True:
                self.emit("load_unload_profile_done", isLoaded=True)
            else:
                self.setup_profile(self.profile_name, "unload")
                # warnings.warn("The profile " + name + " is loaded by other applications")

    def handle_disconnect_headset_id(self, result_dic):
        print("Disconnect headset " + self.headset_id)
        self.headset_id = ""

    def handle_mental_command_active_action_id(self, result_dic):
        self.emit("get_mc_active_action_done", data=result_dic)

    def handle_mental_command_training_threshold(self, result_dic):
        self.emit("mc_training_threshold_done", data=result_dic)

    def handle_mental_command_brain_map_id(self, result_dic):
        self.emit("mc_brainmap_done", data=result_dic)

    def handle_sensitivity_request_id(self, result_dic):
        self.emit("mc_action_sensitivity_done", data=result_dic)

    def handle_create_record_request_id(self, result_dic):
        self.record_id = result_dic["record"]["uuid"]
        self.emit("create_record_done", data=result_dic["record"])

    def handle_stop_record_request_id(self, result_dic):
        self.emit("stop_record_done", data=result_dic["record"])

    def handle_export_record_id(self, result_dic):
        # handle data lable
        success_export = []
        for record in result_dic["success"]:
            record_id = record["recordId"]
            success_export.append(record_id)

        for record in result_dic["failure"]:
            record_id = record["recordId"]
            failure_msg = record["message"]
            print("export_record resp failure cases: " + record_id + ":" + failure_msg)

        self.emit("export_record_done", data=success_export)

    def handle_inject_marker_request_id(self, result_dic):
        self.emit("inject_marker_done", data=result_dic["marker"])

    def handle_update_marker_request_id(self, result_dic):
        self.emit("update_marker_done", data=result_dic["marker"])

    def handle_error(self, recv_dic):
        req_id = recv_dic["id"]
        print("handle_error: request Id " + str(req_id))
        self.emit("inform_error", error_data=recv_dic["error"])

    def handle_warning(self, warning_dic):
        if self.debug:
            print(warning_dic)
        warning_code = warning_dic["code"]
        warning_msg = warning_dic["message"]
        if warning_code == ACCESS_RIGHT_GRANTED:
            # call authorize again
            self.authorize()
        elif warning_code == HEADSET_CONNECTED:
            # query headset again then create session
            self.query_headset()
        elif warning_code == CORTEX_AUTO_UNLOAD_PROFILE:
            self.profile_name = ""
        elif warning_code == CORTEX_STOP_ALL_STREAMS:
            # print(warning_msg['behavior'])
            session_id = warning_msg["sessionId"]
            if session_id == self.session_id:
                self.emit("warn_cortex_stop_all_sub", data=session_id)
                self.session_id = ""

    def handle_stream_data(self, result_dic):
        if result_dic.get("com") is not None:
            com_data = {}
            com_data["action"] = result_dic["com"][0]
            com_data["power"] = result_dic["com"][1]
            com_data["time"] = result_dic["time"]
            self.emit("new_com_data", data=com_data)
        elif result_dic.get("fac") is not None:
            fe_data = {}
            fe_data["eyeAct"] = result_dic["fac"][0]  # eye action
            fe_data["uAct"] = result_dic["fac"][1]  # upper action
            fe_data["uPow"] = result_dic["fac"][2]  # upper action power
            fe_data["lAct"] = result_dic["fac"][3]  # lower action
            fe_data["lPow"] = result_dic["fac"][4]  # lower action power
            fe_data["time"] = result_dic["time"]
            self.emit("new_fe_data", data=fe_data)
        elif result_dic.get("eeg") is not None:
            eeg_data = {}
            eeg_data["eeg"] = result_dic["eeg"]
            eeg_data["eeg"].pop()  # remove markers
            eeg_data["time"] = result_dic["time"]
            self.emit("new_eeg_data", data=eeg_data)
        elif result_dic.get("mot") is not None:
            mot_data = {}
            mot_data["mot"] = result_dic["mot"]
            mot_data["time"] = result_dic["time"]
            self.emit("new_mot_data", data=mot_data)
        elif result_dic.get("dev") is not None:
            dev_data = {}
            dev_data["signal"] = result_dic["dev"][1]
            dev_data["dev"] = result_dic["dev"][2]
            dev_data["batteryPercent"] = result_dic["dev"][3]
            dev_data["time"] = result_dic["time"]
            self.emit("new_dev_data", data=dev_data)
        elif result_dic.get("met") is not None:
            met_data = {}
            met_data["met"] = result_dic["met"]
            met_data["time"] = result_dic["time"]
            self.emit("new_met_data", data=met_data)
        elif result_dic.get("pow") is not None:
            pow_data = {}
            pow_data["pow"] = result_dic["pow"]
            pow_data["time"] = result_dic["time"]
            self.emit("new_pow_data", data=pow_data)
        elif result_dic.get("sys") is not None:
            sys_data = result_dic["sys"]
            self.emit("new_sys_data", data=sys_data)
        else:
            print(result_dic)

    def on_message(self, *args):
        recv_dic = json.loads(args[1])
        if "sid" in recv_dic:
            self.handle_stream_data(recv_dic)
        elif "result" in recv_dic:
            self.handle_result(recv_dic)
        elif "error" in recv_dic:
            self.handle_error(recv_dic)
        elif "warning" in recv_dic:
            self.handle_warning(recv_dic["warning"])
        else:
            raise KeyError

    def query_headset(self):
        print("query headset --------------------------------")
        query_headset_request = {
            "jsonrpc": "2.0",
            "id": QUERY_HEADSET_ID,
            "method": "queryHeadsets",
            "params": {},
        }
        if self.debug:
            print(
                "queryHeadsets request \n", json.dumps(query_headset_request, indent=4)
            )

        self.ws.send(json.dumps(query_headset_request, indent=4))

    def connect_headset(self, headset_id):
        print("connect headset --------------------------------")
        connect_headset_request = {
            "jsonrpc": "2.0",
            "id": CONNECT_HEADSET_ID,
            "method": "controlDevice",
            "params": {"command": "connect", "headset": headset_id},
        }
        if self.debug:
            print(
                "controlDevice request \n",
                json.dumps(connect_headset_request, indent=4),
            )

        self.ws.send(json.dumps(connect_headset_request, indent=4))

    def request_access(self):
        print("request access --------------------------------")
        request_access_request = {
            "jsonrpc": "2.0",
            "method": "requestAccess",
            "params": {"clientId": self.client_id, "clientSecret": self.client_secret},
            "id": REQUEST_ACCESS_ID,
        }

        self.ws.send(json.dumps(request_access_request, indent=4))

    def has_access_right(self):
        print("check has access right --------------------------------")
        has_access_request = {
            "jsonrpc": "2.0",
            "method": "hasAccessRight",
            "params": {"clientId": self.client_id, "clientSecret": self.client_secret},
            "id": HAS_ACCESS_RIGHT_ID,
        }
        self.ws.send(json.dumps(has_access_request, indent=4))

    def authorize(self):
        print("authorize --------------------------------")
        authorize_request = {
            "jsonrpc": "2.0",
            "method": "authorize",
            "params": {
                "clientId": self.client_id,
                "clientSecret": self.client_secret,
                "license": self.license,
                "debit": self.debit,
            },
            "id": AUTHORIZE_ID,
        }

        if self.debug:
            print("auth request \n", json.dumps(authorize_request, indent=4))

        self.ws.send(json.dumps(authorize_request))

    def create_session(self):
        if self.session_id != "":
            warnings.warn("There is existed session " + self.session_id)
            return

        print("create session --------------------------------")
        create_session_request = {
            "jsonrpc": "2.0",
            "id": CREATE_SESSION_ID,
            "method": "createSession",
            "params": {
                "cortexToken": self.auth,
                "headset": self.headset_id,
                "status": "active",
            },
        }

        if self.debug:
            print(
                "create session request \n",
                json.dumps(create_session_request, indent=4),
            )

        self.ws.send(json.dumps(create_session_request))

    def close_session(self):
        print("close session --------------------------------")
        close_session_request = {
            "jsonrpc": "2.0",
            "id": CREATE_SESSION_ID,
            "method": "updateSession",
            "params": {
                "cortexToken": self.auth,
                "session": self.session_id,
                "status": "close",
            },
        }

        self.ws.send(json.dumps(close_session_request))

    def get_cortex_info(self):
        print("get cortex version --------------------------------")
        get_cortex_info_request = {
            "jsonrpc": "2.0",
            "method": "getCortexInfo",
            "id": GET_CORTEX_INFO_ID,
        }

        self.ws.send(json.dumps(get_cortex_info_request))

    """
        Prepare steps include:
        Step 1: check access right. If user has not granted for the application, requestAccess will be called
        Step 2: authorize: to generate a Cortex access token which is required parameter of many APIs
        Step 3: Connect a headset. If no wanted headet is set, the first headset in the list will be connected.
                If you use EPOC Flex headset, you should connect the headset with a proper mappings via EMOTIV Launcher first
        Step 4: Create a working session with the connected headset
        Returns
        -------
        None
        """

    def do_prepare_steps(self):
        print("do_prepare_steps--------------------------------")
        # check access right
        self.has_access_right()

    def disconnect_headset(self):
        print("disconnect headset --------------------------------")
        disconnect_headset_request = {
            "jsonrpc": "2.0",
            "id": DISCONNECT_HEADSET_ID,
            "method": "controlDevice",
            "params": {"command": "disconnect", "headset": self.headset_id},
        }

        self.ws.send(json.dumps(disconnect_headset_request))

    def sub_request(self, stream):
        print("subscribe request --------------------------------")
        sub_request_json = {
            "jsonrpc": "2.0",
            "method": "subscribe",
            "params": {
                "cortexToken": self.auth,
                "session": self.session_id,
                "streams": stream,
            },
            "id": SUB_REQUEST_ID,
        }
        if self.debug:
            print("subscribe request \n", json.dumps(sub_request_json, indent=4))

        self.ws.send(json.dumps(sub_request_json))

    def unsub_request(self, stream):
        print("unsubscribe request --------------------------------")
        unsub_request_json = {
            "jsonrpc": "2.0",
            "method": "unsubscribe",
            "params": {
                "cortexToken": self.auth,
                "session": self.session_id,
                "streams": stream,
            },
            "id": UNSUB_REQUEST_ID,
        }
        if self.debug:
            print("unsubscribe request \n", json.dumps(unsub_request_json, indent=4))

        self.ws.send(json.dumps(unsub_request_json))

    def extract_data_labels(self, stream_name, stream_cols):
        labels = {}
        labels["streamName"] = stream_name

        data_labels = []
        if stream_name == "eeg":
            # remove MARKERS
            data_labels = stream_cols[:-1]
        elif stream_name == "dev":
            # get cq header column except battery, signal and battery percent
            data_labels = stream_cols[2]
        else:
            data_labels = stream_cols

        labels["labels"] = data_labels
        print(labels)
        self.emit("new_data_labels", data=labels)

    def query_profile(self):
        print("query profile --------------------------------")
        query_profile_json = {
            "jsonrpc": "2.0",
            "method": "queryProfile",
            "params": {
                "cortexToken": self.auth,
            },
            "id": QUERY_PROFILE_ID,
        }

        if self.debug:
            print("query profile request \n", json.dumps(query_profile_json, indent=4))
            print("\n")

        self.ws.send(json.dumps(query_profile_json))

    def get_current_profile(self):
        print("get current profile:")
        get_profile_json = {
            "jsonrpc": "2.0",
            "method": "getCurrentProfile",
            "params": {
                "cortexToken": self.auth,
                "headset": self.headset_id,
            },
            "id": GET_CURRENT_PROFILE_ID,
        }

        if self.debug:
            print("get current profile json:\n", json.dumps(get_profile_json, indent=4))
            print("\n")

        self.ws.send(json.dumps(get_profile_json))

    def setup_profile(self, profile_name, status):
        print("setup profile: " + status + " -------------------------------- ")
        setup_profile_json = {
            "jsonrpc": "2.0",
            "method": "setupProfile",
            "params": {
                "cortexToken": self.auth,
                "headset": self.headset_id,
                "profile": profile_name,
                "status": status,
            },
            "id": SETUP_PROFILE_ID,
        }

        if self.debug:
            print("setup profile json:\n", json.dumps(setup_profile_json, indent=4))
            print("\n")

        self.ws.send(json.dumps(setup_profile_json))

    def train_request(self, detection, action, status):
        print("train request --------------------------------")
        train_request_json = {
            "jsonrpc": "2.0",
            "method": "training",
            "params": {
                "cortexToken": self.auth,
                "detection": detection,
                "session": self.session_id,
                "action": action,
                "status": status,
            },
            "id": TRAINING_ID,
        }
        if self.debug:
            print("training request:\n", json.dumps(train_request_json, indent=4))
            print("\n")

        self.ws.send(json.dumps(train_request_json))

    def create_record(self, title, **kwargs):
        print("create record --------------------------------")

        if len(title) == 0:
            warnings.warn(
                "Empty record_title. Please fill the record_title before running script."
            )
            # close socket
            self.close()
            return

        params_val = {
            "cortexToken": self.auth,
            "session": self.session_id,
            "title": title,
        }

        for key, value in kwargs.items():
            params_val.update({key: value})

        create_record_request = {
            "jsonrpc": "2.0",
            "method": "createRecord",
            "params": params_val,
            "id": CREATE_RECORD_REQUEST_ID,
        }
        if self.debug:
            print(
                "create record request:\n", json.dumps(create_record_request, indent=4)
            )

        self.ws.send(json.dumps(create_record_request))

    def stop_record(self):
        print("stop record --------------------------------")
        stop_record_request = {
            "jsonrpc": "2.0",
            "method": "stopRecord",
            "params": {"cortexToken": self.auth, "session": self.session_id},
            "id": STOP_RECORD_REQUEST_ID,
        }
        if self.debug:
            print("stop record request:\n", json.dumps(stop_record_request, indent=4))
        self.ws.send(json.dumps(stop_record_request))

    def export_record(
        self, folder, stream_types, export_format, record_ids, version, **kwargs
    ):
        print("export record --------------------------------: ")
        # validate destination folder
        if len(folder) == 0:
            warnings.warn(
                "Invalid folder parameter. Please set a writable destination folder for exporting data."
            )
            # close socket
            self.close()
            return

        params_val = {
            "cortexToken": self.auth,
            "folder": folder,
            "format": export_format,
            "streamTypes": stream_types,
            "recordIds": record_ids,
        }

        if export_format == "CSV":
            params_val.update({"version": version})

        for key, value in kwargs.items():
            params_val.update({key: value})

        export_record_request = {
            "jsonrpc": "2.0",
            "id": EXPORT_RECORD_ID,
            "method": "exportRecord",
            "params": params_val,
        }

        if self.debug:
            print(
                "export record request \n", json.dumps(export_record_request, indent=4)
            )

        self.ws.send(json.dumps(export_record_request))

    def inject_marker_request(self, time, value, label, **kwargs):
        print("inject marker --------------------------------")
        params_val = {
            "cortexToken": self.auth,
            "session": self.session_id,
            "time": time,
            "value": value,
            "label": label,
        }

        for key, value in kwargs.items():
            params_val.update({key: value})

        inject_marker_request = {
            "jsonrpc": "2.0",
            "id": INJECT_MARKER_REQUEST_ID,
            "method": "injectMarker",
            "params": params_val,
        }
        if self.debug:
            print(
                "inject marker request \n", json.dumps(inject_marker_request, indent=4)
            )
        self.ws.send(json.dumps(inject_marker_request))

    def update_marker_request(self, markerId, time, **kwargs):
        print("update marker --------------------------------")
        params_val = {
            "cortexToken": self.auth,
            "session": self.session_id,
            "markerId": markerId,
            "time": time,
        }

        for key, value in kwargs.items():
            params_val.update({key: value})

        update_marker_request = {
            "jsonrpc": "2.0",
            "id": UPDATE_MARKER_REQUEST_ID,
            "method": "updateMarker",
            "params": params_val,
        }
        if self.debug:
            print(
                "update marker request \n", json.dumps(update_marker_request, indent=4)
            )
        self.ws.send(json.dumps(update_marker_request))

    def get_mental_command_action_sensitivity(self, profile_name):
        print("get mental command sensitivity ------------------")
        sensitivity_request = {
            "id": SENSITIVITY_REQUEST_ID,
            "jsonrpc": "2.0",
            "method": "mentalCommandActionSensitivity",
            "params": {
                "cortexToken": self.auth,
                "profile": profile_name,
                "status": "get",
            },
        }
        if self.debug:
            print(
                "get mental command sensitivity \n",
                json.dumps(sensitivity_request, indent=4),
            )

        self.ws.send(json.dumps(sensitivity_request))

    def set_mental_command_action_sensitivity(self, profile_name, values):
        print("set mental command sensitivity ------------------")
        sensitivity_request = {
            "id": SENSITIVITY_REQUEST_ID,
            "jsonrpc": "2.0",
            "method": "mentalCommandActionSensitivity",
            "params": {
                "cortexToken": self.auth,
                "profile": profile_name,
                "session": self.session_id,
                "status": "set",
                "values": values,
            },
        }
        if self.debug:
            print(
                "set mental command sensitivity \n",
                json.dumps(sensitivity_request, indent=4),
            )

        self.ws.send(json.dumps(sensitivity_request))

    def get_mental_command_active_action(self, profile_name):
        print("get mental command active action ------------------")
        command_active_request = {
            "id": MENTAL_COMMAND_ACTIVE_ACTION_ID,
            "jsonrpc": "2.0",
            "method": "mentalCommandActiveAction",
            "params": {
                "cortexToken": self.auth,
                "profile": profile_name,
                "status": "get",
            },
        }
        if self.debug:
            print(
                "get mental command active action \n",
                json.dumps(command_active_request, indent=4),
            )

        self.ws.send(json.dumps(command_active_request))

    def set_mental_command_active_action(self, actions):
        print("set mental command active action ------------------")
        command_active_request = {
            "id": SET_MENTAL_COMMAND_ACTIVE_ACTION_ID,
            "jsonrpc": "2.0",
            "method": "mentalCommandActiveAction",
            "params": {
                "cortexToken": self.auth,
                "session": self.session_id,
                "status": "set",
                "actions": actions,
            },
        }

        if self.debug:
            print(
                "set mental command active action \n",
                json.dumps(command_active_request, indent=4),
            )

        self.ws.send(json.dumps(command_active_request))

    def get_mental_command_brain_map(self, profile_name):
        print("get mental command brain map ------------------")
        brain_map_request = {
            "id": MENTAL_COMMAND_BRAIN_MAP_ID,
            "jsonrpc": "2.0",
            "method": "mentalCommandBrainMap",
            "params": {
                "cortexToken": self.auth,
                "profile": profile_name,
                "session": self.session_id,
            },
        }
        if self.debug:
            print(
                "get mental command brain map \n",
                json.dumps(brain_map_request, indent=4),
            )
        self.ws.send(json.dumps(brain_map_request))

    def get_mental_command_training_threshold(self, profile_name):
        print("get mental command training threshold -------------")
        training_threshold_request = {
            "id": MENTAL_COMMAND_TRAINING_THRESHOLD,
            "jsonrpc": "2.0",
            "method": "mentalCommandTrainingThreshold",
            "params": {"cortexToken": self.auth, "session": self.session_id},
        }
        if self.debug:
            print(
                "get mental command training threshold \n",
                json.dumps(training_threshold_request, indent=4),
            )
        self.ws.send(json.dumps(training_threshold_request))


# -------------------------------------------------------------------
# -------------------------------------------------------------------


class QueryAPI:
    def __init__(self, url, queue, debug=False):
        super().__init__()
        self.url = url
        self.queue = queue
        self.debug = bool(debug)
        self.is_open = False
        self._stopped = False
        self._trigger = threading.Event()
        self._responded = threading.Event()
        self._response = None
        self._responded.set()

    def trigger(self, timeout=None):
        if not self._trigger.is_set() and self._responded.is_set():
            self._responded.clear()
            self._response = None
            self._trigger.set()
            self.wait(timeout)
        return self._response

    def wait(self, timeout=None):
        self._responded.wait(timeout)

    def join(self):
        self.transmit_thread.join()
        self.websock_thread.join()

    def close(self):
        self.is_open = False
        self._stopped = True
        self.ws.close()

    def open(self):
        # websocket.enableTrace(True)
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_open=self.on_open,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        threadName = "AIWebsockThread:-{:%Y%m%d%H%M%S}".format(datetime.utcnow())

        # As default, a Emotiv self-signed certificate is required.
        # If you don't want to use the certificate, please replace by the below line  by sslopt={"cert_reqs": ssl.CERT_NONE}
        sslopt = {
            "ca_certs": "./rootCA.pem",
            "cert_reqs": ssl.CERT_REQUIRED,
        }
        sslopt = {"cert_reqs": ssl.CERT_NONE}

        self.websock_thread = threading.Thread(
            target=self.ws.run_forever, args=(None, sslopt), name=threadName
        )
        self.websock_thread.start()

        threadName = "TransmitThread:-{:%Y%m%d%H%M%S}".format(datetime.utcnow())
        self.transmit_thread = threading.Thread(
            target=self.handler, args=(), name=threadName
        )
        self.transmit_thread.start()

    def handler(self):
        while not self._stopped:
            time.sleep(0.001)
            if not self.is_open:
                continue
            if self.queue.empty():
                continue
            data = self.queue.get()
            triggered = self._trigger.is_set()
            if triggered:
                self._trigger.clear()

            self.ws.send(json.dumps({"triggered": triggered, "values": data}))
            self.queue.task_done()

    def print(self, *args, **kwargs):
        if self.debug:
            print(*args, **kwargs)

    def on_open(self, *args, **kwargs):
        self.is_open = True
        self.print("websocket opened")

    def on_error(self, *args):
        if len(args) == 2:
            self.print(str(args[1]))

    def on_close(self, *args, **kwargs):
        self.is_open = False
        self.print("on_close")
        self.print(args[1])

    def on_message(self, *args):
        data = json.loads(args[1])
        self._response = data
        self._responded.set()


# -------------------------------------------------------------------

if __name__ == "__main__":
    main(*sys.argv[1:])

# -----------------------------------------------------------
