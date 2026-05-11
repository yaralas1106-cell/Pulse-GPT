from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import json
import threading
import time
import traceback

try:
    import Queue as queue  # Python 2
except ImportError:
    import queue  # Python 3

DEFAULT_PORT = 9877
HOST = "localhost"


def create_instance(c_instance):
    return AbletonMCP(c_instance)


class AbletonMCP(ControlSurface):

    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self.log_message("AbletonMCP Remote Script initializing...")
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False
        self._song = self.song()
        self.start_server()
        self.log_message("AbletonMCP initialized")
        self.show_message("AbletonMCP: Listening on port " + str(DEFAULT_PORT))

    def disconnect(self):
        self.running = False
        if self.server:
            try:
                self.server.close()
            except:
                pass
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(1.0)
        ControlSurface.disconnect(self)

    def start_server(self):
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, DEFAULT_PORT))
            self.server.listen(5)
            self.running = True
            self.server_thread = threading.Thread(target=self._server_thread)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.log_message("Server started on port " + str(DEFAULT_PORT))
        except Exception as e:
            self.log_message("Error starting server: " + str(e))

    def _server_thread(self):
        self.server.settimeout(1.0)
        while self.running:
            try:
                client, address = self.server.accept()
                client_thread = threading.Thread(target=self._handle_client, args=(client,))
                client_thread.daemon = True
                client_thread.start()
                self.client_threads.append(client_thread)
                self.client_threads = [t for t in self.client_threads if t.is_alive()]
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.log_message("Accept error: " + str(e))
                time.sleep(0.5)

    def _handle_client(self, client):
        client.settimeout(None)
        buffer = ''
        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        break
                    try:
                        buffer += data.decode('utf-8')
                    except AttributeError:
                        buffer += data
                    try:
                        command = json.loads(buffer)
                        buffer = ''
                        response = self._process_command(command)
                        try:
                            client.sendall(json.dumps(response).encode('utf-8'))
                        except AttributeError:
                            client.sendall(json.dumps(response))
                    except ValueError:
                        continue
                except Exception as e:
                    error_response = {"status": "error", "message": str(e)}
                    try:
                        client.sendall(json.dumps(error_response).encode('utf-8'))
                    except:
                        break
                    if not isinstance(e, ValueError):
                        break
        except Exception as e:
            self.log_message("Client handler error: " + str(e))
        finally:
            try:
                client.close()
            except:
                pass

    def _process_command(self, command):
        command_type = command.get("type", "")
        params = command.get("params", {})
        response = {"status": "success", "result": {}}

        try:
            if command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                response["result"] = self._get_track_info(params.get("track_index", 0))
            elif command_type == "get_tempo":
                response["result"] = {"tempo": self._song.tempo}
            elif command_type in [
                "create_midi_track", "set_track_name", "create_clip",
                "add_notes_to_clip", "set_clip_name", "set_tempo",
                "fire_clip", "stop_clip", "start_playback", "stop_playback",
                "load_instrument_or_effect", "load_browser_item",
                "create_arrangement_clip", "add_notes_to_arrangement_clip",
                "set_device_parameter",
            ]:
                response_queue = queue.Queue()

                def main_thread_task():
                    try:
                        result = self._dispatch_main_thread(command_type, params)
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Main thread error: " + str(e))
                        response_queue.put({"status": "error", "message": str(e)})

                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    main_thread_task()

                try:
                    task_response = response_queue.get(timeout=10.0)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for Ableton"
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            response["status"] = "error"
            response["message"] = str(e)

        return response

    def _dispatch_main_thread(self, command_type, params):
        if command_type == "create_midi_track":
            return self._create_midi_track(params.get("index", -1))
        elif command_type == "set_track_name":
            return self._set_track_name(params.get("track_index", 0), params.get("name", ""))
        elif command_type == "set_tempo":
            self._song.tempo = float(params.get("tempo", 120))
            return {"tempo": self._song.tempo}
        elif command_type == "create_clip":
            return self._create_clip(
                params.get("track_index", 0),
                params.get("clip_index", 0),
                params.get("length", 4.0),
            )
        elif command_type == "add_notes_to_clip":
            return self._add_notes_to_clip(
                params.get("track_index", 0),
                params.get("clip_index", 0),
                params.get("notes", []),
            )
        elif command_type == "set_clip_name":
            return self._set_clip_name(
                params.get("track_index", 0),
                params.get("clip_index", 0),
                params.get("name", ""),
            )
        elif command_type == "create_arrangement_clip":
            return self._create_arrangement_clip(
                params.get("track_index", 0),
                params.get("position", 0.0),
                params.get("length", 16.0),
            )
        elif command_type == "add_notes_to_arrangement_clip":
            return self._add_notes_to_arrangement_clip(
                params.get("track_index", 0),
                params.get("clip_index", 0),
                params.get("notes", []),
            )
        elif command_type == "set_device_parameter":
            return self._set_device_parameter(
                params.get("track_index", 0),
                params.get("device_index", -1),
                params.get("param_name", ""),
                params.get("value", 0),
            )
        elif command_type == "load_instrument_or_effect":
            return self._load_browser_item(
                params.get("track_index", 0),
                params.get("uri", ""),
            )
        elif command_type == "fire_clip":
            return self._fire_clip(params.get("track_index", 0), params.get("clip_index", 0))
        elif command_type == "stop_clip":
            return self._stop_clip(params.get("track_index", 0), params.get("clip_index", 0))
        elif command_type == "start_playback":
            self._song.start_playing()
            return {"playing": self._song.is_playing}
        elif command_type == "stop_playback":
            self._song.stop_playing()
            return {"playing": self._song.is_playing}
        return {}

    # ── implementations ───────────────────────────────────────────────────────

    def _get_session_info(self):
        return {
            "tempo": self._song.tempo,
            "track_count": len(self._song.tracks),
        }

    def _get_track_info(self, track_index):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        return {
            "index": track_index,
            "name": track.name,
            "is_midi_track": track.has_midi_input,
        }

    def _create_midi_track(self, index):
        self._song.create_midi_track(index)
        new_index = len(self._song.tracks) - 1 if index == -1 else index
        return {"index": new_index, "name": self._song.tracks[new_index].name}

    def _set_track_name(self, track_index, name):
        self._song.tracks[track_index].name = name
        return {"name": name}

    def _create_clip(self, track_index, clip_index, length):
        track = self._song.tracks[track_index]
        slot = track.clip_slots[clip_index]
        if not slot.has_clip:
            slot.create_clip(length)
        return {"length": slot.clip.length}

    def _add_notes_to_clip(self, track_index, clip_index, notes):
        track = self._song.tracks[track_index]
        clip = track.clip_slots[clip_index].clip
        # Accept both "start" and "start_time" key names
        live_notes = tuple(
            (
                int(n.get("pitch", 60)),
                float(n.get("start_time", n.get("start", 0.0))),
                float(n.get("duration", 0.25)),
                int(n.get("velocity", 100)),
                bool(n.get("mute", False)),
            )
            for n in notes
        )
        clip.set_notes(live_notes)
        return {"note_count": len(notes)}

    def _set_clip_name(self, track_index, clip_index, name):
        self._song.tracks[track_index].clip_slots[clip_index].clip.name = name
        return {"name": name}

    def _create_arrangement_clip(self, track_index, position, length):
        track = self._song.tracks[track_index]
        track.create_clip(position, length)
        return {"created": True, "position": position, "length": length}

    def _add_notes_to_arrangement_clip(self, track_index, clip_index, notes):
        track = self._song.tracks[track_index]
        if not track.arrangement_clips:
            raise RuntimeError("No arrangement clips on track")
        clip = track.arrangement_clips[clip_index]
        live_notes = tuple(
            (
                int(n.get("pitch", 60)),
                float(n.get("start_time", n.get("start", 0.0))),
                float(n.get("duration", 0.25)),
                int(n.get("velocity", 100)),
                bool(n.get("mute", False)),
            )
            for n in notes
        )
        clip.set_notes(live_notes)
        return {"note_count": len(notes)}

    def _set_device_parameter(self, track_index, device_index, param_name, value):
        track = self._song.tracks[track_index]
        device = track.devices[device_index]
        for param in device.parameters:
            if param.name.lower() == param_name.lower():
                param.value = float(value)
                return {"param": param.name, "value": param.value}
        raise RuntimeError("Parameter not found: " + param_name)

    def _load_browser_item(self, track_index, uri):
        app = self.application()
        item = self._find_browser_item_by_uri(app.browser, uri)
        if not item:
            return {"loaded": False, "warning": "URI not found: " + uri}
        self._song.view.selected_track = self._song.tracks[track_index]
        app.browser.load_item(item)
        return {"loaded": True, "item_name": item.name}

    def _find_browser_item_by_uri(self, node, uri, depth=0):
        if depth > 8:
            return None
        if hasattr(node, "uri") and node.uri == uri:
            return node
        if hasattr(node, "instruments"):
            for cat in [node.instruments, node.sounds, node.drums,
                        node.audio_effects, node.midi_effects]:
                found = self._find_browser_item_by_uri(cat, uri, depth + 1)
                if found:
                    return found
            return None
        if hasattr(node, "children"):
            for child in node.children:
                found = self._find_browser_item_by_uri(child, uri, depth + 1)
                if found:
                    return found
        return None

    def _fire_clip(self, track_index, clip_index):
        self._song.tracks[track_index].clip_slots[clip_index].fire()
        return {"fired": True}

    def _stop_clip(self, track_index, clip_index):
        self._song.tracks[track_index].clip_slots[clip_index].stop()
        return {"stopped": True}
