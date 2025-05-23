import threading
import time 
import sys
import socket # For socket.gaierror

# Correctly import pyic components from the lib directory
try:
    from lib.pyic import irc_client
    from lib.irc_msg import irc_msg
except ImportError:
    sys.path.insert(0, './lib')
    from pyic import irc_client
    from irc_msg import irc_msg


class IRCManager:
    def __init__(self, ui_callback):
        self.ui_callback = ui_callback
        self.irc_client = None
        self.is_connected = False
        self.receive_thread = None
        self.should_run_thread = False
        self.nick = ""
        self.server = ""
        self.port = 0
        self.initial_channels = []

    def _handle_connection_success(self):
        self.is_connected = True
        if self.initial_channels:
            for channel in self.initial_channels:
                if self.irc_client:
                    self.irc_client.join(channel)
                    self.ui_callback({
                        'type': 'status',
                        'message': f"Joining channel: {channel}"
                    })
        self.ui_callback({
            'type': 'status',
            'message': f"Successfully connected to {self.server} as {self.nick}"
        })

    def _irc_loop(self):
        try:
            self._handle_connection_success()

            while self.should_run_thread and self.irc_client:
                msg_object = self.irc_client.getmsg()

                if msg_object is None:
                    if self.should_run_thread:
                        self.ui_callback({'type': 'error', 'message': 'Connection lost unexpectedly.'})
                    break

                if msg_object.ctcp:
                    ctcp_parts = msg_object.ctcp_msg.upper().split(" ", 1)
                    ctcp_command = ctcp_parts[0]
                    
                    if ctcp_command == "PING":
                        reply_arg = msg_object.ctcp_msg.split(" ", 1)[1] if " " in msg_object.ctcp_msg else ""
                        pong_reply = f"NOTICE {msg_object.by} :\x01PONG {reply_arg}\x01\r\n" # Corrected EOL
                        try:
                            if self.irc_client.sock: # Check if socket still exists
                                self.irc_client.sock.sendall(pong_reply.encode('utf-8', 'ignore'))
                        except Exception as e:
                            self.ui_callback({'type': 'error', 'message': f"Failed to send CTCP PONG: {e}"})
                        continue 
                    elif ctcp_command == "VERSION":
                        # Already handled by pyic.getmsg()
                        pass

                event = {
                    'type': msg_object.type,
                    'by': msg_object.by,
                    'origin': msg_object.origin,
                    'to': msg_object.to,
                    'message': msg_object.msg,
                    'raw': msg_object.raw,
                    'is_private': msg_object.private,
                    'ctcp': msg_object.ctcp,
                    'ctcp_msg': msg_object.ctcp_msg if msg_object.ctcp else "",
                    'params': getattr(msg_object, 'params', []),
                    'kicked': getattr(msg_object, 'kicked', None)
                }
                self.ui_callback(event)

        except ConnectionRefusedError:
            self.ui_callback({'type': 'error', 'message': f"Connection refused by {self.server}:{self.port}"})
        except socket.gaierror:
            self.ui_callback({'type': 'error', 'message': f"Could not resolve server: {self.server}"})
        except socket.timeout: # Catch explicit timeout during getmsg or initial connection parts
            self.ui_callback({'type': 'error', 'message': f"Connection timed out to {self.server}"})
        except Exception as e:
            if self.should_run_thread:
                self.ui_callback({'type': 'error', 'message': f"IRC loop error: {str(e)}"})
        finally:
            self.is_connected = False
            self.should_run_thread = False
            if self.irc_client and hasattr(self.irc_client, 'sock') and self.irc_client.sock:
                try:
                    self.irc_client.sock.close()
                except Exception:
                    pass
            self.irc_client = None


    def connect(self, nick: str, server: str, port: int, channels: list[str] = None, ssl_conn: bool = False, user_password: str = None, server_password: str = None):
        if self.is_connected:
            self.ui_callback({'type': 'error', 'message': 'Already connected. Please disconnect first.'})
            return False

        self.nick = nick
        self.server = server
        self.port = port
        self.initial_channels = channels if channels else []

        self.ui_callback({'type': 'status', 'message': f"Connecting to {server}:{port} as {nick}..."})
        
        try:
            self.irc_client = irc_client(
                nick=nick,
                server=server,
                port=port,
                ssl=ssl_conn,
                username=nick,
                fullname=nick,
                passwd=user_password,
                serverpasswd=server_password
            )
        except socket.gaierror as e:
            self.ui_callback({'type': 'error', 'message': f"Could not resolve server name: {server}. Details: {e}"})
            self.irc_client = None
            return False
        except ConnectionRefusedError as e:
            self.ui_callback({'type': 'error', 'message': f"Connection actively refused by server: {server}:{port}. Details: {e}"})
            self.irc_client = None
            return False
        except socket.timeout as e: # Catch connection timeout
            self.ui_callback({'type': 'error', 'message': f"Connection attempt timed out to {server}:{port}. Details: {e}"})
            self.irc_client = None
            return False
        except Exception as e: # Catch other potential errors from irc_client.__init__
            self.ui_callback({'type': 'error', 'message': f"Failed to connect: {str(e)}"})
            self.irc_client = None
            return False

        self.should_run_thread = True
        self.receive_thread = threading.Thread(target=self._irc_loop, daemon=True)
        self.receive_thread.start()
        return True

    def disconnect(self):
        if not self.is_connected and not self.irc_client and not self.should_run_thread:
            self.ui_callback({'type': 'status', 'message': 'Not currently connected or connecting.'})
            return

        self.ui_callback({'type': 'status', 'message': 'Disconnecting...'})
        self.should_run_thread = False 

        if self.irc_client:
            try:
                if hasattr(self.irc_client, 'sock') and self.irc_client.sock: # Check if socket exists
                     self.irc_client.quit("Rio IRC Client disconnecting")
            except Exception as e:
                # This might happen if socket is already closed, not critical for disconnect sequence
                self.ui_callback({'type': 'warning', 'message': f"Error sending QUIT (socket may be closed): {e}"})
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=3.0) # Wait for the thread to finish
        
        if self.is_connected or self.irc_client is not None: # If still considered connected or client exists
            self.is_connected = False
            self.irc_client = None # Ensure client is None
            self.ui_callback({'type': 'status', 'message': 'Disconnected.'})


    def process_input(self, target: str, user_input: str):
        if not self.is_connected or not self.irc_client:
            self.ui_callback({'type': 'error', 'message': 'Not connected.'})
            return False

        parts = user_input.split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command.startswith("/"):
            if command == "/me":
                if args:
                    ctcp_action_string = f"\x01ACTION {args}\x01" # Corrected CTCP format
                    self.irc_client.sendmsg(target, ctcp_action_string)
                    self.ui_callback({
                        'type': 'self_action', 
                        'by': self.nick, 
                        'to': target, 
                        'message': args 
                    })
                    return True
                else:
                    self.ui_callback({'type': 'error', 'message': 'Usage: /me <message>'})
                    return False
            
            elif command == "/nick":
                if args:
                    new_nickname = args.strip()
                    self.irc_client.change_nick(new_nickname)
                    self.ui_callback({'type': 'status', 'message': f"Attempting to change nick to: {new_nickname}"})
                    return True
                else:
                    self.ui_callback({'type': 'error', 'message': 'Usage: /nick <new_nickname>'})
                    return False

            elif command == "/whois":
                if args:
                    queried_nickname = args.strip()
                    self.irc_client.send_whois(queried_nickname)
                    self.ui_callback({'type': 'status', 'message': f"Requesting WHOIS for: {queried_nickname}"})
                    return True
                else:
                    self.ui_callback({'type': 'error', 'message': 'Usage: /whois <nickname>'})
                    return False
            
            elif command == "/join":
                 if args:
                    self.join_channel_action(args.strip())
                    return True
                 else:
                    self.ui_callback({'type': 'error', 'message': 'Usage: /join <#channel>'})
                    return False
            elif command == "/part":
                 if args:
                    self.part_channel_action(args.strip())
                    return True
                 else: 
                    if target and (target.startswith("#") or target.startswith("&")):
                        self.part_channel_action(target)
                        return True
                    else:
                        self.ui_callback({'type': 'error', 'message': 'Usage: /part <#channel> or use in a channel context.'})
                        return False
            elif command == "/close": # Added /close command
                if target: 
                    self.ui_callback({'type': 'client_command_close_context', 'target_context_id': target})
                    return True
                else:
                    self.ui_callback({'type': 'error', 'message': 'No current context to close.'})
                    return False
            else: 
                self.ui_callback({'type': 'error', 'message': f"Unknown command: {command}"})
                return False
        
        else: 
            self.irc_client.sendmsg(target, user_input)
            return True

    def send_channel_message(self, channel: str, message: str):
        if self.is_connected and self.irc_client:
            self.irc_client.sendmsg(channel, message)
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot send message.'})
        return False

    def send_private_message(self, nick: str, message: str):
        if self.is_connected and self.irc_client:
            self.irc_client.sendmsg(nick, message)
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot send message.'})
        return False

    def join_channel_action(self, channel: str):
        if self.is_connected and self.irc_client:
            self.irc_client.join(channel)
            self.ui_callback({'type': 'status', 'message': f"Attempting to join channel: {channel}"})
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot join channel.'})
        return False

    def part_channel_action(self, channel: str):
        if self.is_connected and self.irc_client:
            self.irc_client.quit_channel(channel) # pyic.py method name
            self.ui_callback({'type': 'status', 'message': f"Attempting to part channel: {channel}"})
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot part channel.'})
        return False

    def send_raw_command(self, command: str):
        if self.is_connected and self.irc_client and hasattr(self.irc_client, 'sock') and self.irc_client.sock:
            self.irc_client.sock.sendall((command + "\r\n").encode('utf-8', 'ignore')) # Use sendall for robustness
            self.ui_callback({'type': 'status', 'message': f"Sent RAW: {command}"})
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot send raw command.'})
        return False
