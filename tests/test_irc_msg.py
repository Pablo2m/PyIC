import unittest

# Assuming irc_msg.py, dcc.py, and irc_codes.py are in the parent directory
# or PYTHONPATH is set up correctly.
try:
    from irc_msg import irc_msg
    from dcc import decompose_dcc_offer # For DCC offer parsing tests
    import irc_codes # To access RPL/ERR constants
except ImportError:
    # Fallback if files are in the parent directory
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from irc_msg import irc_msg
    from dcc import decompose_dcc_offer
    import irc_codes

class TestIRCMessageParsing(unittest.TestCase):
    def test_placeholder(self):
        # This is a placeholder to ensure the file runs.
        # Will be replaced with actual tests.
        self.assertTrue(True)

    def test_privmsg_channel(self):
        raw_line = ":Nick!user@host PRIVMSG #channel :Hello world!"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "PRIVMSG")
        self.assertEqual(msg.msg, "Hello world!")
        self.assertEqual(msg.raw, raw_line)
        self.assertFalse(msg.ctcp)
        self.assertFalse(msg.multiline)
        self.assertFalse(msg.multiline_end)

    def test_privmsg_user(self):
        raw_line = ":Sender!~ident@server.com PRIVMSG Recipient :Hi there!"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Sender")
        self.assertEqual(msg.origin, "~ident@server.com")
        self.assertEqual(msg.to, "Recipient")
        self.assertEqual(msg.type, "PRIVMSG")
        self.assertEqual(msg.msg, "Hi there!")
        self.assertEqual(msg.raw, raw_line)

    def test_privmsg_no_prefix(self):
        raw_line = "PRIVMSG #channel :Message without sender"
        msg = irc_msg(raw_line)
        self.assertIsNone(msg.by)
        self.assertIsNone(msg.origin)
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "PRIVMSG")
        self.assertEqual(msg.msg, "Message without sender")
        self.assertEqual(msg.raw, raw_line)

    def test_notice_channel(self):
        raw_line = ":Nick!user@host NOTICE #channel :This is a notice."
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "NOTICE")
        self.assertEqual(msg.msg, "This is a notice.")
        self.assertEqual(msg.raw, raw_line)

    def test_join_channel(self):
        raw_line = ":Nick!user@host JOIN #newchannel"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertEqual(msg.to, "#newchannel") # target of JOIN is the channel
        self.assertEqual(msg.type, "JOIN")
        self.assertEqual(msg.msg, "#newchannel") # for JOIN, msg is the channel joined
        self.assertEqual(msg.raw, raw_line)

    def test_join_channel_with_key(self):
        raw_line = ":Nick!user@host JOIN #lockedchannel key123"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertEqual(msg.to, "#lockedchannel")
        self.assertEqual(msg.type, "JOIN")
        self.assertEqual(msg.msg, "#lockedchannel key123") # msg includes channel and key

    def test_part_channel(self):
        raw_line = ":Nick!user@host PART #channel :Leaving now"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertEqual(msg.to, "#channel") # target of PART is the channel
        self.assertEqual(msg.type, "PART")
        self.assertEqual(msg.msg, "Leaving now")
        self.assertEqual(msg.raw, raw_line)

    def test_part_channel_no_reason(self):
        raw_line = ":Nick!user@host PART #channel"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "PART")
        self.assertIsNone(msg.msg) # No reason given

    def test_quit_message(self):
        raw_line = ":Nick!user@host QUIT :Gone for lunch"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertIsNone(msg.to) # QUIT doesn't have a target in the typical sense
        self.assertEqual(msg.type, "QUIT")
        self.assertEqual(msg.msg, "Gone for lunch")
        self.assertEqual(msg.raw, raw_line)

    def test_quit_no_message(self):
        raw_line = ":Nick!user@host QUIT"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertIsNone(msg.to)
        self.assertEqual(msg.type, "QUIT")
        self.assertIsNone(msg.msg) # No quit message

    def test_kick_user(self):
        raw_line = ":OpNick!op@host KICK #channel BadUser :Reason for kick"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "OpNick")
        self.assertEqual(msg.origin, "op@host")
        self.assertEqual(msg.to, "#channel") # Channel where kick occurred
        self.assertEqual(msg.type, "KICK")
        self.assertEqual(msg.params, ["#channel", "BadUser"])
        self.assertEqual(msg.msg, "Reason for kick") # Kicked user is a param, msg is reason
        self.assertEqual(msg.kicked, "BadUser")
        self.assertEqual(msg.raw, raw_line)

    def test_kick_user_no_reason(self):
        raw_line = ":OpNick!op@host KICK #channel AnotherUser"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "OpNick")
        self.assertEqual(msg.origin, "op@host")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "KICK")
        self.assertEqual(msg.params, ["#channel", "AnotherUser"])
        self.assertEqual(msg.kicked, "AnotherUser")
        self.assertEqual(msg.msg, "AnotherUser") # If no reason, msg is the kicked user
        self.assertEqual(msg.raw, raw_line)

    def test_mode_channel_set(self):
        raw_line = ":OpNick!op@host MODE #channel +m"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "OpNick")
        self.assertEqual(msg.origin, "op@host")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "MODE")
        self.assertEqual(msg.msg, "+m")
        self.assertEqual(msg.params, ["#channel", "+m"])
        self.assertEqual(msg.raw, raw_line)

    def test_mode_user_set_on_channel(self):
        raw_line = ":OpNick!op@host MODE #channel +o TargetUser"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "OpNick")
        self.assertEqual(msg.origin, "op@host")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "MODE")
        self.assertEqual(msg.msg, "+o TargetUser")
        self.assertEqual(msg.params, ["#channel", "+o", "TargetUser"])
        self.assertEqual(msg.raw, raw_line)

    def test_mode_user_set(self): # User mode by user themselves
        raw_line = ":MyNick!me@host MODE MyNick :+i"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "MyNick")
        self.assertEqual(msg.origin, "me@host")
        self.assertEqual(msg.to, "MyNick") # Target is the user
        self.assertEqual(msg.type, "MODE")
        self.assertEqual(msg.msg, "+i") # The mode change is the message
        self.assertEqual(msg.params, ["MyNick", "+i"])
        self.assertEqual(msg.raw, raw_line)

    def test_ping(self):
        raw_line = "PING :irc.server.com"
        msg = irc_msg(raw_line)
        self.assertIsNone(msg.by)
        self.assertIsNone(msg.origin)
        self.assertIsNone(msg.to) # PING target is in the message part
        self.assertEqual(msg.type, "PING")
        self.assertEqual(msg.msg, "irc.server.com")
        self.assertEqual(msg.raw, raw_line)

    def test_ping_with_prefix(self): # Less common but possible
        raw_line = ":irc.server.org PING :irc.server.org"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "irc.server.org") # Server itself is the 'by'
        self.assertIsNone(msg.origin) # Server messages often don't have a user@host origin
        self.assertIsNone(msg.to)
        self.assertEqual(msg.type, "PING")
        self.assertEqual(msg.msg, "irc.server.org")

    def test_pong(self):
        raw_line = ":Nick!user@host PONG :irc.server.com" # Client responding to PING
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertIsNone(msg.to) # PONG target is in the message part
        self.assertEqual(msg.type, "PONG")
        self.assertEqual(msg.msg, "irc.server.com")
        self.assertEqual(msg.raw, raw_line)

    def test_pong_server_to_server(self):
        raw_line = ":server1.com PONG server2.com :server1.com"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "server1.com")
        self.assertIsNone(msg.origin)
        self.assertEqual(msg.to, "server2.com") # First param after command is target
        self.assertEqual(msg.type, "PONG")
        self.assertEqual(msg.msg, "server1.com") # Last param is the message

    def test_error(self):
        raw_line = "ERROR :Closing link: (user@host) [Client exited]"
        msg = irc_msg(raw_line)
        self.assertIsNone(msg.by)
        self.assertIsNone(msg.origin)
        self.assertIsNone(msg.to)
        self.assertEqual(msg.type, "ERROR")
        self.assertEqual(msg.msg, "Closing link: (user@host) [Client exited]")
        self.assertEqual(msg.raw, raw_line)

    def test_numeric_rpl_welcome(self):
        raw_line = ":irc.server.com 001 MyNick :Welcome to the Internet Relay Network MyNick!user@host"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "irc.server.com")
        self.assertIsNone(msg.origin)
        self.assertEqual(msg.to, "MyNick") # Target of the numeric
        self.assertEqual(msg.type, irc_codes.RPL_WELCOME) # Check against imported constant
        self.assertEqual(msg.type_str, "001") # Also check the string representation
        self.assertEqual(msg.msg, "Welcome to the Internet Relay Network MyNick!user@host")
        self.assertEqual(msg.raw, raw_line)
        self.assertEqual(msg.params, ["MyNick"]) # Params before the trailing message

    def test_numeric_rpl_topic(self):
        raw_line = ":irc.server.com 332 MyNick #channel :This is the channel topic"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "irc.server.com")
        self.assertIsNone(msg.origin)
        self.assertEqual(msg.to, "MyNick") # The user receiving the topic info
        self.assertEqual(msg.type, irc_codes.RPL_TOPIC)
        self.assertEqual(msg.type_str, "332")
        self.assertEqual(msg.msg, "This is the channel topic")
        self.assertEqual(msg.params, ["MyNick", "#channel"])
        self.assertEqual(msg.raw, raw_line)

    def test_numeric_rpl_namreply(self): # Example of multiple middle parameters
        raw_line = ":irc.server.com 353 MyNick = #channel :@OpUser +VoiceUser User1 User2"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "irc.server.com")
        self.assertEqual(msg.to, "MyNick")
        self.assertEqual(msg.type, irc_codes.RPL_NAMREPLY)
        self.assertEqual(msg.type_str, "353")
        self.assertEqual(msg.params, ["MyNick", "=", "#channel"])
        self.assertEqual(msg.msg, "@OpUser +VoiceUser User1 User2")
        self.assertEqual(msg.raw, raw_line)

    def test_numeric_err_nosuchnick(self):
        raw_line = ":irc.server.com 401 MyNick NonExistentNick :No such nick/channel"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "irc.server.com")
        self.assertEqual(msg.to, "MyNick") # User who got the error
        self.assertEqual(msg.type, irc_codes.ERR_NOSUCHNICK)
        self.assertEqual(msg.type_str, "401")
        self.assertEqual(msg.params, ["MyNick", "NonExistentNick"])
        self.assertEqual(msg.msg, "No such nick/channel")
        self.assertEqual(msg.raw, raw_line)

    def test_numeric_with_no_prefix(self): # Some servers might send numerics without prefix
        raw_line = "372 MyNick :- MOTD line here"
        msg = irc_msg(raw_line)
        self.assertIsNone(msg.by)
        self.assertIsNone(msg.origin)
        self.assertEqual(msg.to, "MyNick")
        self.assertEqual(msg.type, irc_codes.RPL_MOTD)
        self.assertEqual(msg.type_str, "372")
        self.assertEqual(msg.params, ["MyNick"])
        self.assertEqual(msg.msg, "- MOTD line here")

    def test_ctcp_version_request(self):
        raw_line = ":Nick!user@host PRIVMSG TargetNick :\x01VERSION\x01"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.origin, "user@host")
        self.assertEqual(msg.to, "TargetNick")
        self.assertEqual(msg.type, "PRIVMSG") # Original type
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, "VERSION")
        self.assertEqual(msg.msg, "\x01VERSION\x01") # Raw CTCP message part
        self.assertEqual(msg.raw, raw_line)

    def test_ctcp_ping_request(self):
        raw_line = ":Nick!user@host PRIVMSG TargetNick :\x01PING 123456789\x01"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.to, "TargetNick")
        self.assertEqual(msg.type, "PRIVMSG")
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, "PING 123456789")
        self.assertEqual(msg.msg, "\x01PING 123456789\x01")
        self.assertEqual(msg.raw, raw_line)

    def test_ctcp_action_message(self): # /me command
        raw_line = ":Nick!user@host PRIVMSG #channel :\x01ACTION waves hello\x01"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "PRIVMSG")
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, "ACTION waves hello")
        self.assertEqual(msg.msg, "\x01ACTION waves hello\x01")
        self.assertEqual(msg.raw, raw_line)

    def test_ctcp_response_notice(self): # CTCP responses are often NOTICEs
        raw_line = ":TargetNick!~tn@remote NOTICE SenderNick :\x01VERSION MyClient v1.0\x01"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "TargetNick")
        self.assertEqual(msg.to, "SenderNick")
        self.assertEqual(msg.type, "NOTICE") # Original type
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, "VERSION MyClient v1.0")
        self.assertEqual(msg.msg, "\x01VERSION MyClient v1.0\x01")
        self.assertEqual(msg.raw, raw_line)

    def test_not_a_ctcp_message(self):
        raw_line = ":Nick!user@host PRIVMSG #channel :This has \x01 but not at start/end."
        msg = irc_msg(raw_line)
        self.assertFalse(msg.ctcp)
        self.assertIsNone(msg.ctcp_msg)
        self.assertEqual(msg.msg, "This has \x01 but not at start/end.")

    def test_ctcp_with_malformed_delimiter(self): # Only one delimiter
        raw_line = ":Nick!user@host PRIVMSG TargetNick :\x01VERSION"
        msg = irc_msg(raw_line)
        self.assertFalse(msg.ctcp) # Should not be detected as CTCP
        self.assertIsNone(msg.ctcp_msg)
        self.assertEqual(msg.msg, "\x01VERSION")

    def test_dcc_send_offer_ctcp(self):
        raw_line = ':FileSender!fs@host PRIVMSG MyNick :\x01DCC SEND "some file.dat" 192.168.0.1 5000 1024\x01'
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "FileSender")
        self.assertEqual(msg.origin, "fs@host")
        self.assertEqual(msg.to, "MyNick")
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, 'DCC SEND "some file.dat" 192.168.0.1 5000 1024')
        
        # Check DCC specific attributes
        self.assertEqual(msg.type, irc_codes.DCC_SEND_OFFER) # Special type for DCC offers
        self.assertEqual(msg.file, "some file.dat")
        self.assertEqual(msg.ip, "192.168.0.1")
        self.assertEqual(msg.port, 5000)
        self.assertEqual(msg.size, 1024)
        self.assertFalse(msg.turbo)
        self.assertEqual(msg.raw, raw_line)

    def test_dcc_tsend_offer_ctcp(self):
        raw_line = ':TurboBot!tb@server PRIVMSG MyNick :\x01DCC TSEND "archive.zip" 10.0.0.2 6001 20480 turbo\x01'
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "TurboBot")
        self.assertEqual(msg.to, "MyNick")
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, 'DCC TSEND "archive.zip" 10.0.0.2 6001 20480 turbo')

        self.assertEqual(msg.type, irc_codes.DCC_SEND_OFFER) # Still uses DCC_SEND_OFFER type
        self.assertEqual(msg.file, "archive.zip")
        self.assertEqual(msg.ip, "10.0.0.2")
        self.assertEqual(msg.port, 6001)
        self.assertEqual(msg.size, 20480)
        self.assertTrue(msg.turbo)
        self.assertEqual(msg.raw, raw_line)

    def test_dcc_send_offer_no_size_ctcp(self):
        raw_line = ':FileSender!fs@host PRIVMSG MyNick :\x01DCC SEND "another file.txt" 192.168.0.10 5050\x01'
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "FileSender")
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, 'DCC SEND "another file.txt" 192.168.0.10 5050')
        
        self.assertEqual(msg.type, irc_codes.DCC_SEND_OFFER)
        self.assertEqual(msg.file, "another file.txt")
        self.assertEqual(msg.ip, "192.168.0.10")
        self.assertEqual(msg.port, 5050)
        self.assertEqual(msg.size, 0) # Default size if not provided
        self.assertFalse(msg.turbo)

    def test_not_a_dcc_offer_ctcp(self): # e.g. CTCP PING but not DCC
        raw_line = ":Nick!user@host PRIVMSG TargetNick :\x01PING 12345\x01"
        msg = irc_msg(raw_line)
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, "PING 12345")
        self.assertEqual(msg.type, "PRIVMSG") # Original type, not DCC_SEND_OFFER
        self.assertIsNone(msg.file)
        self.assertIsNone(msg.ip)
        self.assertIsNone(msg.port)
        self.assertIsNone(msg.size)
        self.assertFalse(msg.turbo)

    def test_malformed_dcc_offer_ctcp(self):
        raw_line = ':FileSender!fs@host PRIVMSG MyNick :\x01DCC SEND "bad offer" only_ip_no_port\x01'
        msg = irc_msg(raw_line)
        self.assertTrue(msg.ctcp)
        self.assertEqual(msg.ctcp_msg, 'DCC SEND "bad offer" only_ip_no_port')
        # It's a CTCP, but not a valid DCC offer, so it should remain PRIVMSG
        # and not populate DCC fields. The `decompose_dcc_offer` call would return False.
        self.assertEqual(msg.type, "PRIVMSG")
        self.assertIsNone(msg.file)
        self.assertIsNone(msg.ip)
        self.assertIsNone(msg.port)
        self.assertIsNone(msg.size)
        self.assertFalse(msg.turbo)

    def test_multiline_motd_start(self):
        raw_line = ":irc.server.com 375 MyNick :- irc.server.com Message of the day -"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.type, irc_codes.RPL_MOTDSTART)
        self.assertEqual(msg.type_str, "375")
        self.assertTrue(msg.multiline)
        self.assertFalse(msg.multiline_end)
        self.assertEqual(msg.msg, "- irc.server.com Message of the day -")

    def test_multiline_motd_line(self):
        raw_line = ":irc.server.com 372 MyNick :- This is a line of the MOTD."
        msg = irc_msg(raw_line)
        self.assertEqual(msg.type, irc_codes.RPL_MOTD)
        self.assertEqual(msg.type_str, "372")
        self.assertTrue(msg.multiline)
        self.assertFalse(msg.multiline_end)
        self.assertEqual(msg.msg, "- This is a line of the MOTD.")

    def test_multiline_motd_end(self):
        raw_line = ":irc.server.com 376 MyNick :End of /MOTD command."
        msg = irc_msg(raw_line)
        self.assertEqual(msg.type, irc_codes.RPL_ENDOFMOTD)
        self.assertEqual(msg.type_str, "376")
        self.assertTrue(msg.multiline)
        self.assertTrue(msg.multiline_end)
        self.assertEqual(msg.msg, "End of /MOTD command.")

    def test_multiline_list_start(self): # RPL_LISTSTART is not standard, but some use similar logic
                                      # Using RPL_STATSLINKINFO as a placeholder for list-like start
                                      # Or just test a command that ISN'T an end/mid of multiline
        raw_line = ":irc.server.com 211 MyNick linkinfo :..." # RPL_STATSLINKINFO
        msg = irc_msg(raw_line, multiline_type_prev=None) # Simulate first line
        # Depending on irc_msg.py's specific multiline start logic, this might need adjustment.
        # For now, assuming it does not set multiline=True unless it's a known start.
        # The provided task description seems to imply irc_msg sets these based on current line's type
        # Let's assume RPL_LISTSTART is 321, RPL_LIST is 322, RPL_LISTEND is 323
        # Since irc_codes.py might not have these, let's use actual numerics
        raw_line_liststart = ":irc.server.com 321 MyNick Channel :Users Name"
        msg_liststart = irc_msg(raw_line_liststart)
        self.assertEqual(msg_liststart.type_str, "321") # Assuming 321 is RPL_LISTSTART
        self.assertTrue(msg_liststart.multiline)
        self.assertFalse(msg_liststart.multiline_end)

    def test_multiline_list_item(self):
        raw_line = ":irc.server.com 322 MyNick #channel 123 :Topic of channel"
        msg = irc_msg(raw_line) # Previous line could have been 321 (LISTSTART)
        self.assertEqual(msg.type, irc_codes.RPL_LIST) # Uses irc_codes.RPL_LIST (322)
        self.assertEqual(msg.type_str, "322")
        self.assertTrue(msg.multiline)
        self.assertFalse(msg.multiline_end)
        self.assertEqual(msg.msg, "Topic of channel")

    def test_multiline_list_end(self):
        raw_line = ":irc.server.com 323 MyNick :End of /LIST"
        msg = irc_msg(raw_line) # Previous line could have been 322 (LIST)
        self.assertEqual(msg.type, irc_codes.RPL_LISTEND) # Uses irc_codes.RPL_LISTEND (323)
        self.assertEqual(msg.type_str, "323")
        self.assertTrue(msg.multiline)
        self.assertTrue(msg.multiline_end)
        self.assertEqual(msg.msg, "End of /LIST")

    def test_not_multiline_privmsg(self):
        raw_line = ":Nick!user@host PRIVMSG #channel :Hello world!"
        msg = irc_msg(raw_line)
        self.assertFalse(msg.multiline)
        self.assertFalse(msg.multiline_end)

    def test_empty_raw_string(self):
        raw_line = ""
        msg = irc_msg(raw_line)
        self.assertIsNone(msg.by)
        self.assertIsNone(msg.origin)
        self.assertIsNone(msg.to)
        self.assertIsNone(msg.type)
        self.assertIsNone(msg.msg)
        self.assertEqual(msg.raw, raw_line)
        self.assertFalse(msg.ctcp)
        self.assertFalse(msg.multiline)
        self.assertFalse(msg.multiline_end)
        self.assertEqual(msg.params, [])

    def test_only_prefix(self):
        raw_line = ":Nick!user@host"
        msg = irc_msg(raw_line)
        # This is technically malformed for a full message,
        # irc_msg might try to parse Nick!user@host as a command.
        # Current implementation of irc_msg.py would make 'Nick!user@host' the command.
        self.assertIsNone(msg.by) # Because the "command" part is now the prefix string
        self.assertIsNone(msg.origin)
        self.assertIsNone(msg.to)
        self.assertEqual(msg.type_str, "Nick!user@host") # The prefix becomes the command if no other command found
        self.assertIsNone(msg.type) # Since "Nick!user@host" is not a known numeric
        self.assertIsNone(msg.msg)
        self.assertEqual(msg.raw, raw_line)
        self.assertEqual(msg.params, [])


    def test_prefix_and_command_no_params(self):
        raw_line = ":irc.server.com PONG" # PONG usually has params, but test absence
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "irc.server.com")
        self.assertIsNone(msg.origin)
        self.assertIsNone(msg.to) # No params, so 'to' is None
        self.assertEqual(msg.type, "PONG")
        self.assertIsNone(msg.msg) # No message part
        self.assertEqual(msg.raw, raw_line)
        self.assertEqual(msg.params, [])

    def test_command_no_params_no_prefix(self):
        raw_line = "QUIT"
        msg = irc_msg(raw_line)
        self.assertIsNone(msg.by)
        self.assertIsNone(msg.origin)
        self.assertIsNone(msg.to)
        self.assertEqual(msg.type, "QUIT")
        self.assertIsNone(msg.msg)
        self.assertEqual(msg.params, [])
        self.assertEqual(msg.raw, raw_line)

    def test_message_with_only_colon_as_message(self):
        raw_line = ":Nick!user@host PRIVMSG #channel ::"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "Nick")
        self.assertEqual(msg.to, "#channel")
        self.assertEqual(msg.type, "PRIVMSG")
        self.assertEqual(msg.msg, ":") # Message is just a colon
        self.assertEqual(msg.raw, raw_line)

    def test_message_with_internal_colons_not_at_start_of_param(self):
        raw_line = ":Nick!user@host PRIVMSG #channel :This is a:test message"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.msg, "This is a:test message")

    def test_message_with_multiple_colons_in_message_part(self):
        raw_line = ":Nick!user@host PRIVMSG #channel ::This ::is a test::"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.msg, ":This ::is a test::")

    def test_prefix_with_no_user_or_host(self): # e.g. server name as prefix
        raw_line = ":irc.example.com NOTICE Auth :*** Looking up your hostname..."
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "irc.example.com") # 'by' is the full prefix if no '!' or '@'
        self.assertIsNone(msg.origin) # No user@host part
        self.assertEqual(msg.to, "Auth")
        self.assertEqual(msg.type, "NOTICE")
        self.assertEqual(msg.msg, "*** Looking up your hostname...")

    def test_prefix_with_user_no_host(self): # :nick!user PING ...
        raw_line = ":MyNick!myuser PING :some_server"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "MyNick")
        self.assertEqual(msg.origin, "myuser") # Origin is just the user part
        self.assertEqual(msg.type, "PING")
        self.assertEqual(msg.msg, "some_server")

    def test_prefix_with_host_no_user(self): # :nick@host PING ... (less common)
        raw_line = ":MyNick@some.host PING :another_server"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "MyNick")
        self.assertEqual(msg.origin, "@some.host") # Origin is just the host part with @
        self.assertEqual(msg.type, "PING")
        self.assertEqual(msg.msg, "another_server")

    def test_numeric_command_too_short(self): # e.g. "00"
        raw_line = ":server 00 MyNick :Short numeric"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "server")
        self.assertEqual(msg.to, "MyNick")
        self.assertEqual(msg.type_str, "00")
        self.assertIsNone(msg.type) # Not a valid 3-digit numeric
        self.assertEqual(msg.msg, "Short numeric")

    def test_non_numeric_command_looks_like_numeric(self):
        raw_line = ":server ABC MyNick :Not a numeric"
        msg = irc_msg(raw_line)
        self.assertEqual(msg.by, "server")
        self.assertEqual(msg.to, "MyNick")
        self.assertEqual(msg.type, "ABC") # Treated as a string command
        self.assertEqual(msg.type_str, "ABC")
        self.assertEqual(msg.msg, "Not a numeric")

if __name__ == '__main__':
    unittest.main()
