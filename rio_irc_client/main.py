import rio
import time
import sys

# Ensure lib is in path for imports within irc_manager if not already handled
# sys.path.insert(0, '.') # If rio_irc_client is the CWD
try:
    from irc_manager import IRCManager # If irc_manager is in PYTHONPATH or CWD
except ImportError:
    # Try to handle common case where main.py is in rio_irc_client and irc_manager.py is also there
    try:
        from .irc_manager import IRCManager # Relative import
    except ImportError:
        # Fallback if running from parent of rio_irc_client
        # This assumes 'rio_irc_client' is a package itself or added to sys.path
        from rio_irc_client.irc_manager import IRCManager

# Color Palette (Dark Theme Example)
COLOR_APP_BG = rio.Color.from_hex("#2B2B2B")
COLOR_CONTAINER_BG = rio.Color.from_hex("#3C3F41")
COLOR_CONTAINER_ALT_BG = rio.Color.from_hex("#45494A")
COLOR_TEXT_PRIMARY = rio.Color.from_hex("#BBBBBB")
COLOR_TEXT_SECONDARY = rio.Color.from_hex("#888888")
COLOR_TEXT_ACCENT = rio.Color.from_hex("#4E8DFF") # Blue
COLOR_TEXT_ERROR = rio.Color.from_hex("#FF5555") # Red
COLOR_TEXT_WARNING = rio.Color.from_hex("#FFA726") # Orange
COLOR_TEXT_SUCCESS = rio.Color.from_hex("#66BB6A") # Green
COLOR_TEXT_SYSTEM = rio.Color.from_hex("#A0A0A0") # Muted gray
COLOR_BORDER = rio.Color.from_hex("#555555")
COLOR_BUTTON_PRIMARY_BG = COLOR_TEXT_ACCENT # Use accent blue
COLOR_BUTTON_DANGER_BG = COLOR_TEXT_ERROR   # Use error red
COLOR_BUTTON_SECONDARY_BG = COLOR_CONTAINER_ALT_BG # Use alt container gray
COLOR_BUTTON_TEXT = rio.Color.from_hex("#FFFFFF") # White text for colored buttons


class RioIrcClientApp(rio.App):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.irc_manager = IRCManager(ui_callback=self.on_irc_event)

        # States
        self.server_address = rio.State("irc.libera.chat")
        self.server_port = rio.State("6667")
        self.nickname = rio.State("RioIRCUser") # Changed default nick
        self.channel_to_join = rio.State("#testing-rio") # Changed default channel
        self.current_channel = rio.State("") 
        self.message_input = rio.State("")
        
        self.chat_messages = rio.State([]) 
        self.user_list = rio.State([]) 
        self.active_channels = rio.State([]) 
        self.connection_status = rio.State("Disconnected")
        
        # States for WHOIS
        self.current_whois_data = rio.State({})
        self.whois_query_nick = rio.State(None)


    def on_irc_event(self, event_data: dict):
        self.call_soon_threadsafe(self._process_irc_event_in_main_thread, event_data)

    def _process_irc_event_in_main_thread(self, event_data: dict):
        event_type = event_data.get('type', 'unknown').upper()
        if isinstance(event_data.get('type'), int) or event_data.get('type', '').isdigit():
            event_type = str(event_data.get('type'))

        raw_msg = event_data.get('raw', '')
        timestamp = time.strftime('%H:%M:%S')
        system_message_channel_context = self.current_channel if self.current_channel else 'system'

        # Specific handling for WHOIS related events
        # Status message from IRCManager indicates a WHOIS query has started via /whois command
        if event_type == 'STATUS' and event_data.get('message', '').startswith("Requesting WHOIS for:"):
            queried_nick = event_data.get('message').split("Requesting WHOIS for:")[1].strip()
            self.whois_query_nick = queried_nick
            self.current_whois_data = {'nick': queried_nick} # Initialize
            # Log the status message itself
            message = event_data.get('message', 'Status updated')
            self.connection_status = message # Or keep existing status, this is just an action status
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': message, 'channel': system_message_channel_context, 'is_system_event': True}]
            self.force_refresh()
            return # Status handled, wait for RPLs

        # If we are in the process of a WHOIS query
        if self.whois_query_nick:
            event_params = event_data.get('params', [])
            
            # Most WHOIS RPLs have the queried nick as the first parameter after our own nick.
            # pyic's irc_msg puts "OurNick TargetNick" in msg.to for some server replies,
            # and params are [<TargetNick>, <param2>, ...].
            # We need to ensure the event is for the nick we are querying.
            # Let's assume the first param (event_params[0]) is the target of the WHOIS reply.
            current_event_target_nick = event_params[0] if event_params else ""

            if current_event_target_nick.lower() == self.whois_query_nick.lower():
                if event_type == 'RPL_WHOISUSER' or event_type == '311':
                    # Params: [<nick>, <user>, <host>, <*>] Message: <real_name>
                    if len(event_params) >= 3: # Should be at least 4 with '*'
                        self.current_whois_data['user'] = event_params[1]
                        self.current_whois_data['host'] = event_params[2]
                    self.current_whois_data['real_name'] = event_data.get('message', '')
                
                elif event_type == 'RPL_WHOISSERVER' or event_type == '312':
                    # Params: [<nick>, <server>] Message: <server_info>
                    if len(event_params) >= 2:
                        self.current_whois_data['server'] = event_params[1]
                    self.current_whois_data['server_info'] = event_data.get('message', '')

                elif event_type == 'RPL_AWAY' or event_type == '301':
                    # Params: [<nick>] Message: <away_message>
                    self.current_whois_data['away'] = event_data.get('message', '')

                elif event_type == 'RPL_WHOISOPERATOR' or event_type == '313':
                    # Params: [<nick>] Message: <text like "is an IRC Operator">
                    self.current_whois_data['operator_info'] = event_data.get('message', '')
                
                elif event_type == 'RPL_WHOISIDLE' or event_type == '317':
                    # Params: [<nick>, <idle_seconds>, <signon_time_unix_ts>] Message: <text like "seconds idle">
                    # pyic doesn't explicitly parse signon_time from message if it's there.
                    # We'll take what's given.
                    idle_str = ""
                    if len(event_params) >= 2:
                        idle_str += event_params[1] # idle_seconds
                    if event_data.get('message'): # Usually "seconds idle" or similar
                        idle_str += f" {event_data.get('message')}"
                    if len(event_params) >= 3: # If signon time is a separate param
                         idle_str += f" (Signon: {time.ctime(int(event_params[2])) if event_params[2].isdigit() else event_params[2]})"
                    self.current_whois_data['idle'] = idle_str.strip()
                
                elif event_type == 'RPL_WHOISCHANNELS' or event_type == '319':
                    # Params: [<nick>] Message: <channel_list e.g., "@#chan1 #chan2">
                    channels_str = event_data.get('message', '')
                    self.current_whois_data['channels'] = self.current_whois_data.get('channels', []) + channels_str.strip().split()

                elif event_type == 'ERR_NOSUCHNICK' or event_type == '401':
                    # Params: [<queried_nick_attempt>] Message: <error_message>
                    error_message = f"WHOIS Error for {self.whois_query_nick}: {event_data.get('message', 'No such nick/channel')}"
                    self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': error_message, 'channel': system_message_channel_context, 'is_error': True}]
                    self.whois_query_nick = None
                    self.current_whois_data = {}
                
                elif event_type == 'RPL_ENDOFWHOIS' or event_type == '318':
                    # Params: [<nick>] Message: <text like "End of /WHOIS list.">
                    whois_strings = [f"--- WHOIS results for {self.whois_query_nick} ---"]
                    data_to_display = self.current_whois_data
                    
                    if data_to_display.get('nick'): # Should always be there from init
                        whois_strings.append(f"Nick: {data_to_display['nick']}")
                    if data_to_display.get('real_name'): whois_strings.append(f"Real Name: {data_to_display['real_name']}")
                    if data_to_display.get('user'): whois_strings.append(f"User: {data_to_display['user']}@{data_to_display.get('host', 'N/A')}")
                    if data_to_display.get('away'): whois_strings.append(f"Status: Away ({data_to_display['away']})")
                    if data_to_display.get('channels'): whois_strings.append(f"Channels: {' '.join(data_to_display['channels'])}")
                    if data_to_display.get('server'): whois_strings.append(f"Server: {data_to_display['server']} ({data_to_display.get('server_info', 'N/A')})")
                    if data_to_display.get('operator_info'): whois_strings.append(f"Info: {data_to_display['operator_info']}")
                    if data_to_display.get('idle'): whois_strings.append(f"Idle: {data_to_display['idle']}")
                    whois_strings.append("--- End of WHOIS ---")

                    for line in whois_strings:
                        self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': line, 'channel': system_message_channel_context, 'is_system_event': True}]
                    
                    self.whois_query_nick = None
                    self.current_whois_data = {}
                
                self.force_refresh()
                # If one of the WHOIS RPLs, we might not want to log it raw or process it further.
                # For now, by returning, we skip other general processing for this event.
                return # WHOIS event handled (or ignored if not for current query nick but whois_query_nick was set)

        # General event processing starts here if not a WHOIS-specific part of an active query
        if event_type == 'STATUS': # General status, not the WHOIS start one
            message = event_data.get('message', 'Status updated')
            self.connection_status = message
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': message, 'channel': system_message_channel_context, 'is_system_event': True}]
        elif event_type == 'ERROR':
            message = event_data.get('message', 'Unknown error')
            error_text = f"ERROR: {message}"
            self.connection_status = error_text 
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': error_text, 'channel': system_message_channel_context, 'is_error': True}]
        elif event_type == 'WARNING':
            message = event_data.get('message', 'Unknown warning')
            warn_text = f"WARNING: {message}"
            # Display warnings in chat for now, could also affect connection_status if desired
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': warn_text, 'channel': system_message_channel_context, 'is_warning': True}]
        elif event_type == 'PRIVMSG':
            sender = event_data.get('by', 'Unknown')
            target = event_data.get('to', 'Unknown').lower() # Channel or your nick
            text = event_data.get('message', '')
            
            # If target is our nick, it's a private message.
            # We need a way to handle PMs, e.g., treat sender as 'channel' for PMs
            effective_channel = target
            if target == self.nickname.lower():
                effective_channel = sender.lower() # Use sender as the 'channel' for PMs

            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': sender, 'text': text, 'channel': effective_channel}]
        elif event_type == 'JOIN':
            who = event_data.get('by', 'Unknown')
            # In pyic, for JOIN, msg.to is the channel
            channel_joined = event_data.get('to', '').lower()
            if not channel_joined: # Fallback if 'to' is empty
                 channel_joined = event_data.get('message','').lower()


            if who.lower() == self.nickname.lower():
                if channel_joined not in self.active_channels:
                    self.active_channels = self.active_channels + [channel_joined]
                self.current_channel = channel_joined
                self.user_list = [] 
                self.irc_manager.send_raw_command(f"NAMES {channel_joined}") # Request names for new channel
            elif channel_joined == self.current_channel:
                 if who not in self.user_list: # Add user if they joined current channel
                    self.user_list = sorted(list(set(self.user_list + [who])), key=str.lower)
        elif event_type == 'PART':
            who = event_data.get('by', 'Unknown')
            channel_parted = event_data.get('to', '').lower() # Channel is in 'to'
            # reason = event_data.get('message', '') # Optional reason

            if who.lower() == self.nickname.lower():
                if channel_parted in self.active_channels:
                    self.active_channels = [ch for ch in self.active_channels if ch != channel_parted]
                if self.current_channel == channel_parted:
                    self.current_channel = self.active_channels[0] if self.active_channels else ""
                    self.user_list = []
            elif channel_parted == self.current_channel:
                self.user_list = [user for user in self.user_list if user.lower() != who.lower()]
        
        elif event_type == 'QUIT': # User quit IRC
            who = event_data.get('by', 'Unknown')
            # reason = event_data.get('message', '')
            # Remove user from all user lists if they were on current channel
            if self.current_channel and who.lower() in {u.lower() for u in self.user_list}:
                 self.user_list = [user for user in self.user_list if user.lower() != who.lower()]
            # Could also iterate all active_channels' user lists if storing them separately
            log_text = f"{who} has quit IRC ({event_data.get('message', '')})."
            # Log this to all active channels the user might have been in, or just current if simpler
            # For now, log to current channel if user was there, or system context
            relevant_channel_for_quit_log = self.current_channel if self.current_channel and who.lower() in {u.lower() for u in self.user_list} else system_message_channel_context
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': log_text, 'channel': relevant_channel_for_quit_log, 'is_system_event': True}]


        elif event_type == 'NICK': # Nick change
            old_nick = event_data.get('by', '')
            new_nick = event_data.get('message', '') # New nick is in message part
            
            nick_change_log = f"{old_nick} is now known as {new_nick}."
            # Log this to all active channels where old_nick might be present
            # For simplicity, log to current channel if user is there, or system.
            # A more advanced approach would update user lists in all relevant active_channels.
            
            if old_nick.lower() == self.nickname.lower():
                self.nickname = new_nick # Update our own nick
                # Log change in all active channels for self
                for ch in self.active_channels:
                    self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': nick_change_log, 'channel': ch, 'is_system_event': True}]
                if not self.active_channels: # If not on any channel, log to system
                     self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': nick_change_log, 'channel': system_message_channel_context, 'is_system_event': True}]


            # Update user list if the user was in the current channel's list
            if self.current_channel:
                new_user_list = []
                changed = False
                for user in self.user_list:
                    if user.lower() == old_nick.lower():
                        new_user_list.append(new_nick)
                        changed = True
                    else:
                        new_user_list.append(user)
                if changed:
                    self.user_list = sorted(list(set(new_user_list)), key=str.lower)
                    # Log the nick change to the current channel if the user was present
                    self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': nick_change_log, 'channel': self.current_channel, 'is_system_event': True}]
            elif old_nick.lower() != self.nickname.lower() : # If not in current channel and not self, log to system
                 self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': nick_change_log, 'channel': system_message_channel_context, 'is_system_event': True}]


        elif event_type == 'RPL_NAMREPLY' or event_type == '353':
            # Example: :server_name 353 YourNick = #channel_name :user1 @user2 +user3
            msg_parts = event_data.get('message', '').split(':')
            names_str = msg_parts[-1].strip() if msg_parts else ''
            
            # Try to extract channel from "YourNick = #channel" or "YourNick @ #channel" part
            # msg.to in pyic for 353 is YourNick = #channel (params[2]) or YourNick @ #channel (params[1])
            # Correct parsing of channel from RPL_NAMREPLY and RPL_ENDOFNAMES is crucial.
            # Assuming event_data['to'] contains "YourNick = #channel" or similar
            # and the actual channel name is the last word starting with # or &
            
            # A more robust way to get channel from RPL_NAMREPLY:
            # The actual message structure from RFC1459 for 353 is:
            # :server 353 <nick> <symbol> <channel> :<names>
            # So, msg.params would be [<nick>, <symbol>, <channel>] and msg.msg is <names>
            # pyic.py's irc_msg.py parses this into:
            # msg.to = <nick> (first param after command)
            # msg.params = [<nick>, <symbol>, <channel>] (all params)
            # msg.msg = <names> (the part after colon)
            # So, if event_data['raw'] is available and parsed by irc_msg,
            # the channel should be in msg_object.params[2]
            # For now, using the 'to' field and splitting is a workaround if params aren't directly in event_data
            channel_for_names = ""
            # For pyic's irc_msg, params[0] is our nick, params[1] is symbol, params[2] is channel
            if 'params' in event_data and len(event_data['params']) >= 3: 
                 channel_for_names = event_data['params'][2].lower()
            # Fallback might be needed if params structure is different from expectation
            
            if channel_for_names == self.current_channel: # Check if these names are for the currently viewed channel
                new_names = [name.lstrip('@+~&%') for name in names_str.split() if name.strip()]
                self.user_list = self.user_list + new_names # Append, will sort/dedupe at ENDOFNAMES
        
        elif event_type == 'RPL_ENDOFNAMES' or event_type == '366':
            # :server 366 <nick> <channel> :End of /NAMES list
            # For pyic's irc_msg, params[0] is our nick, params[1] is channel
            channel_for_names = ""
            if 'params' in event_data and len(event_data['params']) >= 2: 
                channel_for_names = event_data['params'][1].lower()

            if channel_for_names == self.current_channel:
                self.user_list = sorted(list(set(self.user_list)), key=str.lower) 
        
        elif event_type == 'KICK':
            kicker = event_data.get('by', 'Unknown')
            channel_kicked_from = event_data.get('to', '').lower()
            # pyic specific: msg.kicked should be event_data['params'][1] if present
            kicked_user = event_data.get('kicked', '') 
            if not kicked_user and 'params' in event_data and len(event_data['params']) > 1:
                kicked_user = event_data['params'][1] # params[0] is channel, params[1] is kicked_user

            reason = event_data.get('message', 'No reason specified')
            # In pyic, if no reason for KICK, msg.msg can be the kicked_user.
            if kicked_user == reason and 'params' in event_data and len(event_data['params']) > 1 : # Check if reason was actually the user
                 actual_reason_parts = raw_msg.split(":", 2) # :Kicker KICK #chan User :Reason
                 if len(actual_reason_parts) > 2:
                     reason = actual_reason_parts[2]
                 else:
                     reason = "No reason specified"

            kick_log_text = f"{kicked_user} was kicked from {channel_kicked_from} by {kicker}. Reason: {reason}"
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': kick_log_text, 'channel': channel_kicked_from, 'is_system_event': True}]

            if kicked_user.lower() == self.nickname.lower(): # We were kicked
                self.connection_status = f"You were kicked from {channel_kicked_from} by {kicker}."
                if channel_kicked_from in self.active_channels:
                    self.active_channels = [ch for ch in self.active_channels if ch != channel_kicked_from]
                if self.current_channel == channel_kicked_from:
                    self.current_channel = self.active_channels[0] if self.active_channels else ""
                    self.user_list = [] 
            elif channel_kicked_from == self.current_channel: 
                 self.user_list = [user for user in self.user_list if user.lower() != kicked_user.lower()]
        
        elif event_type == 'RPL_TOPIC' or event_type == '332': # Topic for channel
            # pyic: params are [OurNick, #channel], message is topic
            channel_topic_is_for = event_data.get('params')[1].lower() if 'params' in event_data and len(event_data['params']) > 1 else system_message_channel_context
            topic_text = event_data.get('message', '')
            topic_log = f"Topic for {channel_topic_is_for}: {topic_text}"
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': topic_log, 'channel': channel_topic_is_for, 'is_system_event': True}]

        elif event_type == 'RPL_NOTOPIC' or event_type == '331': # No topic set
            # pyic: params are [OurNick, #channel], message is "No topic is set"
            channel_no_topic = event_data.get('params')[1].lower() if 'params' in event_data and len(event_data['params']) > 1 else system_message_channel_context
            no_topic_log = f"No topic set for {channel_no_topic}."
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': no_topic_log, 'channel': channel_no_topic, 'is_system_event': True}]
        
        else: # Default handling for other message types
            # This is where other specific RPLs or commands could be logged if not handled above.
            # For example, raw server notices not covered by STATUS/ERROR/WARNING.
            # We need to be careful not to double-log things already processed.
            # For now, if it's not one of the above, it might be a raw server message or unhandled.
            # Consider adding a generic log for any `raw_msg` if it wasn't specifically handled.
            # This can be noisy, so commented out for now.
            # if raw_msg and event_type not in ['PRIVMSG', 'JOIN', 'PART', 'QUIT', 'NICK', 'KICK', ...other handled numerics...]:
            #    log_entry = f"[{timestamp}] ({event_type}) RAW: {raw_msg.strip()}"
            #    self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'Server', 'text': log_entry, 'channel': system_message_channel_context, 'is_system_event': True}]
            pass


        self.force_refresh()


    def do_connect_disconnect(self):
        if self.irc_manager.is_connected:
            self.irc_manager.disconnect()
        else:
            try:
                port = int(self.server_port)
                # Clear chat messages and user lists from previous connection
                self.chat_messages = []
                self.user_list = []
                self.active_channels = []
                self.current_channel = ""

                self.irc_manager.connect(
                    nick=self.nickname,
                    server=self.server_address,
                    port=port,
                    channels=[self.channel_to_join.lower()] if self.channel_to_join else [],
                    ssl_conn=(port == 6697 or port == 9999 or port == 7000 or port == 7070) # Common SSL ports
                )
            except ValueError:
                self._process_irc_event_in_main_thread({'type':'ERROR', 'message':'Invalid port number.'})
        self.force_refresh()


    def do_join_channel(self):
        chan_to_join_val = self.channel_to_join.lower()
        if self.irc_manager.is_connected and chan_to_join_val:
            if not chan_to_join_val.startswith("#") and not chan_to_join_val.startswith("&"):
                 self._process_irc_event_in_main_thread({'type':'ERROR', 'message':'Channel name must start with # or &.'})
                 return
            self.irc_manager.join_channel_action(chan_to_join_val)
        elif not self.irc_manager.is_connected:
             self._process_irc_event_in_main_thread({'type':'ERROR', 'message':'Not connected.'})
        self.force_refresh()
        
    def do_send_ui_message(self):
        if self.irc_manager.is_connected and self.message_input and self.current_channel:
            self.irc_manager.send_channel_message(self.current_channel, self.message_input)
            # Optimistically add to chat_messages for responsiveness
            self.chat_messages = self.chat_messages + [{'timestamp': time.strftime('%H:%M:%S'), 'sender': self.nickname, 'text': self.message_input, 'channel': self.current_channel}]
            self.message_input = "" 
        elif not self.irc_manager.is_connected:
            self._process_irc_event_in_main_thread({'type':'ERROR', 'message':'Not connected.'})
        elif not self.current_channel:
            self._process_irc_event_in_main_thread({'type':'ERROR', 'message':'No active channel selected.'})
        self.force_refresh()

    def select_channel(self, channel_name: str):
        self.current_channel = channel_name.lower()
        self.user_list = [] 
        if self.irc_manager.is_connected:
            self.irc_manager.send_raw_command(f"NAMES {self.current_channel}")
        self.force_refresh()

    def build(self) -> rio.Component:
        connect_button_text = "Disconnect" if self.irc_manager.is_connected else "Connect"
        connect_button_color_name = "danger" if self.irc_manager.is_connected else "primary"

        connection_bar = rio.Row(
            rio.TextInput(text=self.server_address, label="Server", width=15, style=rio.TextStyle(color=COLOR_TEXT_PRIMARY), label_style=rio.TextStyle(color=COLOR_TEXT_SECONDARY)),
            rio.TextInput(text=self.server_port, label="Port", width=6, style=rio.TextStyle(color=COLOR_TEXT_PRIMARY), label_style=rio.TextStyle(color=COLOR_TEXT_SECONDARY)),
            rio.TextInput(text=self.nickname, label="Nickname", width=10, style=rio.TextStyle(color=COLOR_TEXT_PRIMARY), label_style=rio.TextStyle(color=COLOR_TEXT_SECONDARY)),
            rio.Button(
                connect_button_text, 
                on_press=self.do_connect_disconnect, 
                # Attempt to use ButtonStyle for custom colors; fallback to Rio's named colors if needed
                style=rio.ButtonStyle(
                    background_color=COLOR_BUTTON_DANGER_BG if self.irc_manager.is_connected else COLOR_BUTTON_PRIMARY_BG,
                    text_color=COLOR_BUTTON_TEXT
                )
                # As a fallback if ButtonStyle is not effective for BG/text: color=connect_button_color_name 
            ),
            spacing=1,
            key="connection_bar",
            background_color=COLOR_CONTAINER_BG,
            padding=0.5,
            border_radius=0.5,
        )

        channel_buttons = []
        for ch_name in self.active_channels:
            is_current = (ch_name == self.current_channel)
            channel_buttons.append(
                rio.Button(
                    ch_name, 
                    on_press=lambda _, ch=ch_name: self.select_channel(ch),
                    style=rio.TextStyle(font_weight="bold" if is_current else "normal"),
                    color="primary" if is_current else "neutral"
                )
            )
        
        channel_list_column = rio.Column(
            rio.Text("Channels", style="heading2"),
            *channel_buttons,
            rio.TextInput(text=self.channel_to_join, label="Join Channel", width="grow"),
            rio.Button("Join", on_press=self.do_join_channel, width="grow"),
            spacing=0.5,
            key="channel_list_ui" # Changed key
        )

        user_list_display = rio.ListView(*[rio.Text(user) for user in self.user_list]) if self.user_list else rio.Text("No users listed.")

        user_list_column = rio.Column(
            rio.Text(f"Users in {self.current_channel}" if self.current_channel else "Users", style="heading2"),
            user_list_display, # Using ListView
            spacing=0.5,
            key="user_list_ui" # Changed key
        )
        
        left_panel = rio.Column(channel_list_column, rio.Spacer(height=1), user_list_column, spacing=1, width=3) # Grid units

        current_channel_msgs_filtered = [msg for msg in self.chat_messages if msg.get('channel') == self.current_channel]
        message_texts = []
        for msg_data in current_channel_msgs_filtered:
            style = rio.TextStyle()
            sender_text = f"<{msg_data['sender']}>"
            if msg_data.get('is_error'):
                style.color = rio.Color.RED
                sender_text = "[System]"
            elif msg_data.get('is_warning'):
                style.color = rio.Color.ORANGE 
                sender_text = "[System]"
            elif msg_data.get('is_system_event'):
                style.color = rio.Color.GRAY # Or some other subtle color
                sender_text = "[System]"

            message_texts.append(
                rio.Text(f"[{msg_data['timestamp']}] {sender_text} {msg_data['text']}", style=style)
            )

        message_display_area = rio.ListView(*message_texts, height="grow") if message_texts else rio.Text("No messages yet for this channel.", align_x=0.5, align_y=0.5)
        
        message_input_field = rio.TextInput(text=self.message_input, label="Message", width="grow")
        send_button = rio.Button("Send", on_press=self.do_send_ui_message, color="primary")
        
        # Python trick: If the input field is focused, pressing Enter should click the send button.
        # This uses Rio's `bind_hotkey` feature on the TextInput.
        message_input_field.bind_hotkey("enter", send_button.press)

        input_bar = rio.Row(
            message_input_field,
            send_button,
            spacing=1,
            key="input_bar"
        )
        
        right_panel = rio.Column(
            rio.Text(f"Messages for: {self.current_channel}" if self.current_channel else "Messages", style="heading2"),
            message_display_area, 
            input_bar, 
            spacing=1, 
            width=9, # Grid units
            height="grow"
        )

        main_area = rio.Row(
            left_panel,
            right_panel,
            spacing=1,
            height="grow" # Allow main area to grow
        )

        return rio.Column(
            connection_bar,
            rio.Text(f"Status: {self.connection_status}", style="italic"),
            main_area,
            spacing=1,
            margin=1,
            width="grow",
            height="grow", # Ensure root column also grows
            key="root_column_ui" # Changed key
        )

app = RioIrcClientApp()
