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

    def on_irc_event(self, event_data: dict):
        self.call_soon_threadsafe(self._process_irc_event_in_main_thread, event_data)

    def _process_irc_event_in_main_thread(self, event_data: dict):
        event_type = event_data.get('type', 'unknown').upper()
        # Fallback for numeric IRC codes if type is not a string command
        if isinstance(event_data.get('type'), int): # Or check if it's a digit string
             event_type = str(event_data.get('type'))

        raw_msg = event_data.get('raw', '')
        timestamp = time.strftime('%H:%M:%S')
        
        # Default channel for system messages if current_channel is not set
        system_message_channel_context = self.current_channel if self.current_channel else 'system'

        if event_type == 'STATUS':
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
            if 'params' in event_data and len(event_data['params']) >= 3: # If irc_msg.params is passed
                 channel_for_names = event_data['params'][2].lower()
            else: # Fallback to trying to parse from 'to' or 'raw' if possible
                to_parts = event_data.get('to','').split() # This is likely just our nick
                raw_parts = raw_msg.split() # :server 353 YourNick = #channel :names
                # Find the channel name in raw_parts
                for part in raw_parts:
                    if part.startswith("#") or part.startswith("&"):
                        channel_for_names = part.lower()
                        break
            
            if channel_for_names == self.current_channel:
                new_names = [name.lstrip('@+~&%') for name in names_str.split() if name.strip()]
                self.user_list = self.user_list + new_names # Append, will sort/dedupe at ENDOFNAMES
        
        elif event_type == 'RPL_ENDOFNAMES' or event_type == '366':
            # :server 366 <nick> <channel> :End of /NAMES list
            channel_for_names = ""
            if 'params' in event_data and len(event_data['params']) >= 2: # Params: [<nick>, <channel>]
                channel_for_names = event_data['params'][1].lower()
            else:
                raw_parts = raw_msg.split()
                for part in raw_parts:
                    if part.startswith("#") or part.startswith("&"):
                        channel_for_names = part.lower()
                        break

            if channel_for_names == self.current_channel:
                self.user_list = sorted(list(set(self.user_list)), key=str.lower) 
        
        elif event_type == 'KICK':
            kicker = event_data.get('by', 'Unknown')
            # In pyic's irc_msg for KICK:
            # msg.to is the channel
            # msg.params[1] (or msg.kicked) is the user kicked
            # msg.msg is the reason
            channel_kicked_from = event_data.get('to', '').lower()
            kicked_user = event_data.get('kicked', '') # Assuming 'kicked' field is populated by irc_msg
            if not kicked_user and 'params' in event_data and len(event_data['params']) > 1:
                kicked_user = event_data['params'][1]

            reason = event_data.get('message', 'No reason specified')
            if kicked_user == reason: # If no reason, pyic sets kicked user as message
                reason = "No reason specified" 
            
            kick_log_text = f"{kicked_user} was kicked from {channel_kicked_from} by {kicker}. Reason: {reason}"
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': kick_log_text, 'channel': channel_kicked_from, 'is_system_event': True}]

            if kicked_user.lower() == self.nickname.lower(): # We were kicked
                self.connection_status = f"You were kicked from {channel_kicked_from} by {kicker}."
                if channel_kicked_from in self.active_channels:
                    self.active_channels = [ch for ch in self.active_channels if ch != channel_kicked_from]
                if self.current_channel == channel_kicked_from:
                    self.current_channel = self.active_channels[0] if self.active_channels else ""
                    self.user_list = [] # Clear user list for the channel we were kicked from
            elif channel_kicked_from == self.current_channel: # Someone else kicked from current channel
                 self.user_list = [user for user in self.user_list if user.lower() != kicked_user.lower()]
        
        elif event_type == 'RPL_TOPIC' or event_type == '332':
            channel_topic_is_for = event_data.get('params')[1].lower() if 'params' in event_data and len(event_data['params']) > 1 else 'unknown_channel'
            topic_text = event_data.get('message', '')
            topic_log = f"Topic for {channel_topic_is_for}: {topic_text}"
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': topic_log, 'channel': channel_topic_is_for, 'is_system_event': True}]

        elif event_type == 'RPL_NOTOPIC' or event_type == '331':
            channel_no_topic = event_data.get('params')[1].lower() if 'params' in event_data and len(event_data['params']) > 1 else 'unknown_channel'
            no_topic_log = f"No topic set for {channel_no_topic}."
            self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'System', 'text': no_topic_log, 'channel': channel_no_topic, 'is_system_event': True}]
        
        # Log unhandled raw messages if they are not covered above explicitly
        # This helps in debugging and seeing what the server is sending.
        # Add a check to see if raw_msg was already part of a handled event.
        # For example, PRIVMSG, JOIN, PART, etc. already add their content.
        # System messages from STATUS, ERROR, WARNING are also added.
        # KICK, NICK, QUIT, TOPIC changes are also logged.
        # Perhaps only log raw for truly unhandled numeric types or commands.
        # This part needs careful consideration to avoid duplicate logging.
        # For now, I'll assume the specific handlers above cover most common cases.
        # A simple approach: if no specific `chat_messages.append` happened for this event, log raw.
        # This is hard to track perfectly without more state.
        # A placeholder for "unhandled" can be:
        # else:
        #    if raw_msg: # And not one of the already handled types by specific logic above
        #        log_entry = f"[{timestamp}] RAW ({event_type}): {raw_msg.strip()}"
        #        self.chat_messages = self.chat_messages + [{'timestamp': timestamp, 'sender': 'Server', 'text': log_entry, 'channel': system_message_channel_context, 'is_system_event': True}]

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
        connection_bar = rio.Row(
            rio.TextInput(text=self.server_address, label="Server", width=15),
            rio.TextInput(text=self.server_port, label="Port", width=6),
            rio.TextInput(text=self.nickname, label="Nickname", width=10),
            rio.Button(connect_button_text, on_press=self.do_connect_disconnect, color="primary" if not self.irc_manager.is_connected else "danger"),
            spacing=1,
            key="connection_bar"
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
