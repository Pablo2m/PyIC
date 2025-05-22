import threading
import time # For potential sleeps or timeouts if needed
import sys
import socket # For socket.gaierror

# Correctly import pyic components from the lib directory
try:
    from lib.pyic import irc_client
    from lib.irc_msg import irc_msg
    # from lib.irc_codes import RPL_ENDOFMOTD # Not strictly needed here
except ImportError:
    sys.path.insert(0, './lib')
    from pyic import irc_client
    from irc_msg import irc_msg
    # from irc_codes import RPL_ENDOFMOTD


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
            # connect_to_server is called in irc_client.__init__
            # The _handle_connection_success is called after irc_client is successfully initialized
            # which means MOTD is processed (or attempted) by irc_client's connect_to_server.
            
            # Moved _handle_connection_success to be called after irc_client is confirmed connected
            # and initial messages (like MOTD end) are processed by irc_client itself.
            # For now, assuming irc_client's __init__ blocks until basic connection is up or fails.
            # If irc_client.connected is True after init, we can proceed.
            if not (self.irc_client and self.irc_client.connected):
                 # This case should ideally be caught during irc_client instantiation in connect()
                 # or immediately after if connect_to_server fails silently.
                 if self.should_run_thread:
                     self.ui_callback({'type': 'error', 'message': 'IRC client not connected after initialization.'})
                 return

            self._handle_connection_success() # Call this now that client is supposedly connected

            while self.should_run_thread and self.irc_client:
                try:
                    msg_object = self.irc_client.getmsg()
                except socket.timeout: # Example of a more specific error
                    if self.should_run_thread: # Only report if we weren't trying to disconnect
                        self.ui_callback({'type': 'warning', 'message': 'Connection timed out. Attempting to reconnect or verify connection.'})
                        # Potentially add reconnect logic or just let it fail if further calls raise errors
                    continue # Or break, depending on desired behavior
                except Exception as e: # Catch other errors from getmsg (like connection closed)
                    if self.should_run_thread:
                        self.ui_callback({'type': 'error', 'message': f'Error receiving message: {str(e)}. Disconnecting.'})
                    break # Exit loop on critical receive error


                if msg_object is None: # Should be caught by Exception above if getmsg raises it
                    if self.should_run_thread:
                        self.ui_callback({'type': 'error', 'message': 'Connection lost unexpectedly (received None).'})
                    break

                # Handle CTCP PING explicitly
                if msg_object.ctcp:
                    ctcp_parts = msg_object.ctcp_msg.upper().split(" ", 1)
                    ctcp_command = ctcp_parts[0]
                    # ctcp_args_upper = ctcp_parts[1] if len(ctcp_parts) > 1 else "" # Not used directly for PING reply arg

                    if ctcp_command == "PING":
                        # Respond to CTCP PING
                        # The sender of the PRIVMSG (msg_object.by) is who we reply to.
                        # The content of the PING (argument) should be sent back in the PONG.
                        reply_arg = msg_object.ctcp_msg.split(" ", 1)[1] if " " in msg_object.ctcp_msg else ""
                        # CTCP PONG reply is sent via NOTICE
                        # Format: NOTICE <target_nick> :\x01PONG <timestamp_or_arg>\x01
                        pong_reply_string = f"NOTICE {msg_object.by} :\x01PONG {reply_arg}\x01\r\n"
                        try:
                            if self.irc_client and self.irc_client.sock:
                                self.irc_client.sock.sendall(pong_reply_string.encode('utf-8', 'ignore'))
                            # Optionally log this event to UI if needed for debugging
                            # self.ui_callback({'type': 'debug', 'message': f"Responded to CTCP PING from {msg_object.by} with PONG {reply_arg}"})
                        except Exception as e:
                            self.ui_callback({'type': 'error', 'message': f"Failed to send CTCP PONG: {e}"})
                        continue # Don't process this PRIVMSG further as a normal message for UI

                    elif ctcp_command == "VERSION":
                        # This is already handled by pyic.getmsg() calling self.irc_client.sendVer()
                        # No action needed here, but we acknowledge it.
                        # self.ui_callback({'type': 'debug', 'message': f"CTCP VERSION request from {msg_object.by} handled by pyic."})
                        # It will still be passed to UI as a CTCP message, which is fine.
                        pass # Let it fall through to the UI callback

                event = {
                    'type': msg_object.type,
                    'by': msg_object.by,
                    'origin': msg_object.origin,
                    'to': msg_object.to,
                    'message': msg_object.msg, # This is the full message part, e.g., "\x01ACTION dances\x01" for CTCP
                    'raw': msg_object.raw,
                    'is_private': getattr(msg_object, 'private', False), # pyic's irc_msg doesn't set this explicitly, but good to have
                    'ctcp': msg_object.ctcp,
                    'ctcp_msg': msg_object.ctcp_msg if msg_object.ctcp else "", # This is the inner content, e.g. "ACTION dances"
                    'params': getattr(msg_object, 'params', []), # Pass params if available
                    'kicked': getattr(msg_object, 'kicked', None) # Pass kicked if available
                }
                self.ui_callback(event)

        except ConnectionRefusedError: # This might be redundant if connect() handles it, but good for loop-time issues
            self.ui_callback({'type': 'error', 'message': f"Connection refused by {self.server}:{self.port}"})
        except socket.gaierror:
            self.ui_callback({'type': 'error', 'message': f"Could not resolve server name: {self.server}. Please check the address and your network."})
        except ConnectionRefusedError: # More specific than generic Exception for this
            self.ui_callback({'type': 'error', 'message': f"Connection actively refused by the server {self.server}:{self.port}."})
        except socket.timeout: # If connect call itself times out
             self.ui_callback({'type': 'error', 'message': f"Connection attempt to {self.server}:{self.port} timed out."})
        except Exception as e: # Catch-all for other errors during the loop or setup
            if self.should_run_thread: # Only show error if not part of a deliberate disconnect
                self.ui_callback({'type': 'error', 'message': f"An unexpected error occurred in IRC loop: {str(e)}"})
        finally:
            self.is_connected = False
            self.should_run_thread = False
            if self.irc_client and hasattr(self.irc_client, 'sock') and self.irc_client.sock:
                try:
                    self.irc_client.sock.close()
                except Exception:
                    pass
            self.irc_client = None
            # Avoid double "Disconnected" if disconnect was called explicitly and already sent one
            # self.ui_callback({'type': 'status', 'message': 'Disconnected.'})


    def connect(self, nick: str, server: str, port: int, channels: list[str] = None, ssl_conn: bool = False, user_password: str = None, server_password: str = None):
        if self.is_connected:
            self.ui_callback({'type': 'error', 'message': 'Already connected. Please disconnect first.'})
            return False

        self.nick = nick
        self.server = server
        self.port = port
        self.initial_channels = channels if channels else []

        self.ui_callback({'type': 'status', 'message': f"Connecting to {server}:{port} as {nick}..."})
        
        # It's tricky to send "Resolving server..." then "Attempting connection..." separately
        # because irc_client's __init__ does it all. We can only catch errors from it.
        try:
            # Attempt to create and connect the IRC client
            self.irc_client = irc_client(
                nick=nick,
                server=server, # This will be resolved and connected to within irc_client
                port=port,
                ssl=ssl_conn,
                username=nick,
                fullname=nick,
                passwd=user_password,
                serverpasswd=server_password
            )
            # If irc_client constructor finishes but connection failed (e.g. bad password, nick in use before MOTD)
            # pyic's connect_to_server might raise an exception or just not set connected.
            # We rely on _irc_loop to check self.irc_client.connected or handle getmsg errors.
            if not self.irc_client.connected: # Check if pyic's internal connected flag is set
                # This path might be hard to reach if irc_client constructor raises error on failure
                self.ui_callback({'type': 'error', 'message': f"Connection to {server} failed. Please check server details, credentials, and network."})
                self.irc_client = None
                return False

        except socket.gaierror: # DNS resolution error
            self.ui_callback({'type': 'error', 'message': f"Could not resolve server: {server}. Check the address."})
            self.irc_client = None
            return False
        except ConnectionRefusedError:
            self.ui_callback({'type': 'error', 'message': f"Connection refused by {server}:{port}."})
            self.irc_client = None
            return False
        except socket.timeout:
            self.ui_callback({'type': 'error', 'message': f"Connection attempt to {server}:{port} timed out."})
            self.irc_client = None
            return False
        except Exception as e: # Other errors during irc_client instantiation (e.g. SSL issues not caught above)
            self.ui_callback({'type': 'error', 'message': f"Failed to initialize connection: {str(e)}"})
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
                if hasattr(self.irc_client, 'sock') and self.irc_client.sock:
                     self.irc_client.quit("Rio IRC Client disconnecting")
            except Exception as e:
                self.ui_callback({'type': 'warning', 'message': f"Error sending QUIT: {e}. Forcing disconnect."})
            # No finally self.irc_client = None here, _irc_loop's finally handles it
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=3.0)
        
        # If the thread never started or died quickly, ensure disconnected state is reported
        if self.is_connected or self.irc_client is not None:
            self.is_connected = False
            self.irc_client = None
            self.ui_callback({'type': 'status', 'message': 'Disconnected.'})


    def send_channel_message(self, channel: str, message: str):
        if self.is_connected and self.irc_client:
            self.irc_client.sendmsg(channel, message)
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot send message.'})
        return False

    def send_private_message(self, nick: str, message: str): # Kept for direct use
        if self.is_connected and self.irc_client:
            self.irc_client.sendmsg(nick, message)
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot send message.'})
        return False

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
                    ctcp_action_string = f"\x01ACTION {args}\x01"
                    self.irc_client.sendmsg(target, ctcp_action_string)
                    # Callback for UI to display own action optimistically
                    self.ui_callback({
                        'type': 'self_action', # Distinguish from incoming actions
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
                    # Server will send a NICK message back, which main.py handles.
                    # We can also send an optimistic status message.
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
            
            # Add other slash commands here in the future e.g. /join, /part, /query
            elif command == "/join":
                 if args:
                    self.join_channel_action(args.strip()) # Use existing method
                    return True
                 else:
                    self.ui_callback({'type': 'error', 'message': 'Usage: /join <#channel>'})
                    return False
            elif command == "/part":
                 if args:
                    self.part_channel_action(args.strip()) # Use existing method
                    return True
                 else: # Part current channel if no args
                    if target and (target.startswith("#") or target.startswith("&")):
                        self.part_channel_action(target)
                        return True
                    else:
                        self.ui_callback({'type': 'error', 'message': 'Usage: /part <#channel> or use in a channel context.'})
                        return False


            else: # Unknown slash command
                self.ui_callback({'type': 'error', 'message': f"Unknown command: {command}"})
                return False
        
        else: # Regular message
            self.irc_client.sendmsg(target, user_input)
            # UI currently handles optimistic display of own messages.
            # If we wanted manager to confirm, add a callback here:
            # self.ui_callback({'type': 'self_message', 'by': self.nick, 'to': target, 'message': user_input})
            return True

    def join_channel_action(self, channel: str):
        if self.is_connected and self.irc_client:
            self.irc_client.join(channel)
            self.ui_callback({'type': 'status', 'message': f"Attempting to join channel: {channel}"})
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot join channel.'})
        return False

    def part_channel_action(self, channel: str):
        if self.is_connected and self.irc_client:
            self.irc_client.quit_channel(channel)
            self.ui_callback({'type': 'status', 'message': f"Attempting to part channel: {channel}"})
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot part channel.'})
        return False

    def send_raw_command(self, command: str):
        if self.is_connected and self.irc_client and hasattr(self.irc_client, 'sock') and self.irc_client.sock:
            self.irc_client.sock.send((command + "\r\n").encode('utf-8'))
            self.ui_callback({'type': 'status', 'message': f"Sent RAW: {command}"})
            return True
        self.ui_callback({'type': 'error', 'message': 'Not connected. Cannot send raw command.'})
        return False
