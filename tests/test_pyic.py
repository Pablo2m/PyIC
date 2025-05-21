import unittest
from unittest.mock import patch, Mock, MagicMock, call # Added call for checking send sequences

# Assuming pyic.py, irc_msg.py, dcc.py, and irc_codes.py are in the parent directory
# or PYTHONPATH is set up correctly.
try:
    from pyic import clean_usr, getline, irc_client
    from irc_msg import irc_msg
    import irc_codes # For RPL/ERR constants and DCC_SEND_OFFER
    import dcc # For dcc.decompose_dcc_offer if needed by irc_msg during tests
except ImportError:
    # Fallback if files are in the parent directory
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from pyic import clean_usr, getline, irc_client
    from irc_msg import irc_msg
    import irc_codes
    import dcc

# Constants for testing
TEST_SERVER = "irc.example.com"
TEST_PORT = 6667
TEST_NICK = "TestNick"
TEST_IDENT = "testident"
TEST_REALNAME = "Test User"
TEST_CHANNEL = "#testchannel"
TEST_SERVERPASS = "serverpassword"
TEST_NICKSERV_PASS = "nickservpassword"


class TestCleanUsr(unittest.TestCase):
    def test_remove_at_symbol(self):
        self.assertEqual(clean_usr("@testuser"), "testuser")

    def test_no_at_symbol(self):
        self.assertEqual(clean_usr("testuser"), "testuser")

    def test_multiple_at_symbols(self):
        # Based on typical behavior, clean_usr likely removes only the first leading '@'
        # or all '@'. Assuming it removes only a leading one if present.
        # If it's supposed to remove all, this test needs adjustment.
        # Let's assume it removes only a leading one based on common usage for channel names.
        self.assertEqual(clean_usr("@@anotheruser"), "@anotheruser") # Assumes only leading @ removed
        self.assertEqual(clean_usr("user@name@test"), "user@name@test") # No leading @

    def test_empty_string(self):
        self.assertEqual(clean_usr(""), "")

    def test_only_at_symbol(self):
        self.assertEqual(clean_usr("@"), "")

    def test_leading_at_with_other_chars(self):
        self.assertEqual(clean_usr("@#channel"), "#channel")


class TestGetline(unittest.TestCase):
    @patch('socket.socket') # We don't need the socket, just a mock object with recv
    def test_getline_simple_lf(self, mock_socket_constructor):
        mock_sock = mock_socket_constructor.return_value
        mock_sock.recv.side_effect = [b'l', b'i', b'n', b'e', b'1', b'\n']
        line = getline(mock_sock)
        self.assertEqual(line, "line1")
        self.assertEqual(mock_sock.recv.call_count, 6)
        mock_sock.recv.assert_has_calls([call(1)] * 6)

    @patch('socket.socket')
    def test_getline_crlf(self, mock_socket_constructor):
        mock_sock = mock_socket_constructor.return_value
        mock_sock.recv.side_effect = [b'l', b'i', b'n', b'e', b'2', b'\r', b'\n']
        line = getline(mock_sock)
        self.assertEqual(line, "line2")
        self.assertEqual(mock_sock.recv.call_count, 7)

    @patch('socket.socket')
    def test_getline_connection_closed_empty_recv(self, mock_socket_constructor):
        mock_sock = mock_socket_constructor.return_value
        mock_sock.recv.return_value = b'' # Simulate connection closed
        with self.assertRaisesRegex(Exception, "Connection closed"):
            getline(mock_sock)
        mock_sock.recv.assert_called_once_with(1)

    @patch('socket.socket')
    def test_getline_connection_closed_after_data(self, mock_socket_constructor):
        mock_sock = mock_socket_constructor.return_value
        mock_sock.recv.side_effect = [b'd', b'a', b't', b'a', b''] # Data then closed
        with self.assertRaisesRegex(Exception, "Connection closed"):
            getline(mock_sock)
        # It should have called recv 5 times before raising the exception
        self.assertEqual(mock_sock.recv.call_count, 5)


    @patch('socket.socket')
    def test_getline_long_line(self, mock_socket_constructor):
        mock_sock = mock_socket_constructor.return_value
        long_string_content = "a" * 4096
        byte_stream = [bytes([char_code]) for char_code in long_string_content.encode('utf-8')] + [b'\n']
        mock_sock.recv.side_effect = byte_stream
        
        line = getline(mock_sock)
        self.assertEqual(line, long_string_content)
        self.assertEqual(mock_sock.recv.call_count, len(long_string_content) + 1)
        
    @patch('socket.socket')
    def test_getline_decode_error(self, mock_socket_constructor):
        mock_sock = mock_socket_constructor.return_value
        # Simulate receiving invalid UTF-8 sequence
        mock_sock.recv.side_effect = [b'\xff', b'\n'] # \xff is not valid UTF-8 start byte
        # The original getline decodes byte by byte with 'ignore' so it might not raise error,
        # but rather ignore/replace the byte. Let's check the behavior.
        # If pyic.py's getline uses .decode(errors='ignore' or 'replace'), this test changes.
        # Assuming it uses default 'strict' for now, or that the issue would manifest as empty/partial.
        # The current getline in pyic.py: `c = self.sock.recv(1).decode("utf-8", "ignore")`
        # So, an invalid byte will be ignored.
        line = getline(mock_sock)
        self.assertEqual(line, "") # \xff is ignored, only \n terminates.

    @patch('socket.socket')
    def test_getline_multiple_lines_in_buffer_stops_at_first_lf(self, mock_socket_constructor):
        mock_sock = mock_socket_constructor.return_value
        # Simulate recv returning more than one byte, with multiple newlines
        # getline is designed to read one byte at a time via sock.recv(1)
        # This test is more about ensuring the loop logic is correct for single byte reads.
        mock_sock.recv.side_effect = [b'f', b'i', b'r', b's', b't', b'\n', b's', b'e', b'c', b'o', b'n', b'd', b'\n']
        line = getline(mock_sock)
        self.assertEqual(line, "first")
        # getline should have stopped after the first \n
        self.assertEqual(mock_sock.recv.call_count, 6)


class TestIrcClientBase(unittest.TestCase):
    """ Base class for irc_client tests that need a mocked client setup """
    def setUp(self):
        # This setup will be more complex, involving mocking socket, etc.
        # For now, a simple placeholder.
        self.mock_socket_patch = patch('pyic.socket.socket')
        self.mock_ssl_wrap_patch = patch('pyic.ssl.wrap_socket')
        self.mock_getline_patch = patch('pyic.getline') # To control server responses

        self.mock_socket_constructor = self.mock_socket_patch.start()
        self.mock_ssl_wrap_socket = self.mock_ssl_wrap_patch.start()
        self.mock_getline = self.mock_getline_patch.start() # Patched for all methods in subclasses

        self.mock_socket_instance = MagicMock(spec=socket.socket)
        self.mock_socket_constructor.return_value = self.mock_socket_instance
        self.mock_ssl_wrap_socket.return_value = self.mock_socket_instance

        # Client is no longer initialized here. Test methods or specialized SetUp methods
        # in subclasses will create client instances.

    def tearDown(self):
        # Stop patches started in setUp if they were assigned to self
        # self.mock_socket_patch.stop() # This was started by decorator/context manager in tests
        # self.mock_ssl_wrap_patch.stop()
        # self.mock_getline_patch.stop() # This was started by decorator/context manager in tests
        # Using patch.stopall() is generally okay if all patches are started with .start()
        # and not as decorators on the test methods themselves or the class.
        # If patches are method/class decorators, they are stopped automatically.
        # Let's be explicit for those started in this setUp.
        if hasattr(self, 'mock_socket_patch') and self.mock_socket_patch.is_started():
             self.mock_socket_patch.stop()
        if hasattr(self, 'mock_ssl_wrap_patch') and self.mock_ssl_wrap_patch.is_started():
             self.mock_ssl_wrap_patch.stop()
        if hasattr(self, 'mock_getline_patch') and self.mock_getline_patch.is_started():
             self.mock_getline_patch.stop()
        # If a test method uses @patch, those are handled automatically.

class TestIrcClientConnection(TestIrcClientBase):
    def test_connect_to_server_success_no_pass_no_ssl(self):
        # Mock getline to simulate server responses during connection
        self.mock_getline.side_effect = [
            f":{TEST_SERVER} 001 {TEST_NICK} :Welcome",
            f"PING :{TEST_SERVER}",
            f":{TEST_SERVER} 376 {TEST_NICK} :End of MOTD",
        ]

        client = irc_client(
            nick=TEST_NICK,
            ident=TEST_IDENT,
            ircrealname=TEST_REALNAME,
            server=TEST_SERVER,
            port=TEST_PORT
        )
        # connect_to_server is called by __init__
        
        self.mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        self.mock_socket_instance.connect.assert_called_once_with((TEST_SERVER, TEST_PORT))
        
        expected_sends = [
            call(f"NICK {TEST_NICK}\r\n".encode("utf-8")),
            call(f"USER {TEST_IDENT} 8 * :{TEST_REALNAME}\r\n".encode("utf-8")),
            call(f"PONG :{TEST_SERVER}\r\n".encode("utf-8")), 
        ]
        # Check that these calls were made in this order among others.
        # The actual calls might include others if the client sends more by default.
        # We can check for a subsequence or specific calls.
        
        # Get all actual calls to send
        all_send_calls = self.mock_socket_instance.send.call_args_list
        
        # Verify NICK and USER are first two, PONG is later
        self.assertEqual(all_send_calls[0], expected_sends[0])
        self.assertEqual(all_send_calls[1], expected_sends[1])
        self.assertIn(expected_sends[2], all_send_calls) # PONG can happen after some getlines

        self.assertTrue(client.connected)
        self.assertEqual(client.current_nick, TEST_NICK)
        self.assertIn(f":{TEST_SERVER} 001 {TEST_NICK} :Welcome", client.motd)
        self.mock_ssl_wrap_socket.assert_not_called()

    def test_connect_to_server_success_with_server_pass_no_ssl(self):
        self.mock_getline.side_effect = [
            f":{TEST_SERVER} 001 {TEST_NICK} :Welcome",
            f":{TEST_SERVER} 376 {TEST_NICK} :End of MOTD",
        ]
        client = irc_client(
            nick=TEST_NICK, ident=TEST_IDENT, ircrealname=TEST_REALNAME,
            server=TEST_SERVER, port=TEST_PORT, serverpasswd=TEST_SERVERPASS
        )
        self.mock_socket_instance.connect.assert_called_once_with((TEST_SERVER, TEST_PORT))
        expected_sends = [
            call(f"PASS {TEST_SERVERPASS}\r\n".encode("utf-8")),
            call(f"NICK {TEST_NICK}\r\n".encode("utf-8")),
            call(f"USER {TEST_IDENT} 8 * :{TEST_REALNAME}\r\n".encode("utf-8")),
        ]
        # Check order of initial commands
        all_send_calls = self.mock_socket_instance.send.call_args_list
        self.assertEqual(all_send_calls[0], expected_sends[0]) # PASS
        self.assertEqual(all_send_calls[1], expected_sends[1]) # NICK
        self.assertEqual(all_send_calls[2], expected_sends[2]) # USER
        self.assertTrue(client.connected)
        self.mock_ssl_wrap_socket.assert_not_called()

    def test_connect_to_server_success_with_nickserv_pass_no_ssl(self):
        self.mock_getline.side_effect = [
            f":{TEST_SERVER} 001 {TEST_NICK} :Welcome",
            f":{TEST_SERVER} 376 {TEST_NICK} :End of MOTD",
            # Add more mock responses if getmsg is called more often by NickServ logic
        ]
        client = irc_client(
            nick=TEST_NICK, ident=TEST_IDENT, ircrealname=TEST_REALNAME,
            server=TEST_SERVER, port=TEST_PORT, passwd=TEST_NICKSERV_PASS
        )
        self.mock_socket_instance.connect.assert_called_once_with((TEST_SERVER, TEST_PORT))
        
        initial_sends = [
            call(f"NICK {TEST_NICK}\r\n".encode("utf-8")),
            call(f"USER {TEST_IDENT} 8 * :{TEST_REALNAME}\r\n".encode("utf-8")),
        ]
        identify_send = call(f"PRIVMSG NickServ :IDENTIFY {TEST_NICKSERV_PASS}\r\n".encode("utf-8"))
        
        all_send_calls = self.mock_socket_instance.send.call_args_list
        
        # Check initial connection calls are present and in order
        self.assertEqual(all_send_calls[0], initial_sends[0]) # NICK
        self.assertEqual(all_send_calls[1], initial_sends[1]) # USER
        # Check NickServ identify call is present after initial calls
        self.assertIn(identify_send, all_send_calls[2:]) # Should be after NICK & USER

        self.assertTrue(client.connected)
        self.mock_ssl_wrap_socket.assert_not_called()

    def test_connect_to_server_success_with_ssl(self):
        self.mock_getline.side_effect = [
            f":{TEST_SERVER} 001 {TEST_NICK} :Welcome",
            f":{TEST_SERVER} 376 {TEST_NICK} :End of MOTD",
        ]
        client = irc_client(
            nick=TEST_NICK, ident=TEST_IDENT, ircrealname=TEST_REALNAME,
            server=TEST_SERVER, port=TEST_PORT, ssl=True
        )
        self.mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        self.mock_ssl_wrap_socket.assert_called_once_with(self.mock_socket_instance)
        self.mock_socket_instance.connect.assert_called_once_with((TEST_SERVER, TEST_PORT))
        
        expected_sends = [
            call(f"NICK {TEST_NICK}\r\n".encode("utf-8")),
            call(f"USER {TEST_IDENT} 8 * :{TEST_REALNAME}\r\n".encode("utf-8")),
        ]
        all_send_calls = self.mock_socket_instance.send.call_args_list
        self.assertEqual(all_send_calls[0], expected_sends[0])
        self.assertEqual(all_send_calls[1], expected_sends[1])
        self.assertTrue(client.connected)

    def test_connect_to_server_fail_connection_error(self):
        self.mock_socket_instance.connect.side_effect = socket.error("Connection refused")
        
        with self.assertRaisesRegex(Exception, "Couldn't connect to server"):
            irc_client(
                nick=TEST_NICK, ident=TEST_IDENT, ircrealname=TEST_REALNAME,
                server=TEST_SERVER, port=TEST_PORT
            )
        self.mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        self.mock_socket_instance.connect.assert_called_once_with((TEST_SERVER, TEST_PORT))
        self.mock_socket_instance.send.assert_not_called()
        self.mock_socket_instance.close.assert_called_once()

    def test_connect_to_server_fail_after_nick_user_sent(self):
        self.mock_getline.side_effect = Exception("Connection closed")

        with self.assertRaisesRegex(Exception, "Connection closed"):
             irc_client(
                nick=TEST_NICK, ident=TEST_IDENT, ircrealname=TEST_REALNAME,
                server=TEST_SERVER, port=TEST_PORT
            )
        
        self.mock_socket_instance.connect.assert_called_once_with((TEST_SERVER, TEST_PORT))
        expected_sends = [
            call(f"NICK {TEST_NICK}\r\n".encode("utf-8")),
            call(f"USER {TEST_IDENT} 8 * :{TEST_REALNAME}\r\n".encode("utf-8")),
        ]
        all_send_calls = self.mock_socket_instance.send.call_args_list
        self.assertEqual(all_send_calls[0], expected_sends[0])
        self.assertEqual(all_send_calls[1], expected_sends[1])
        self.mock_socket_instance.close.assert_called_once()


class TestIrcClientGetMsg(TestIrcClientBase):
    def setUp(self):
        super().setUp() # Call base class setUp to initialize mocks
        # Initialize a client for these tests, assuming connection is already handled/mocked
        self.client = irc_client(
            nick=TEST_NICK, server=None # Prevent auto-connect
        )
        self.client.sock = self.mock_socket_instance
        self.client.connected = True
        self.client.current_nick = TEST_NICK # Set current_nick as it's used in some logic

    def test_getmsg_from_buffer(self):
        mock_msg1 = irc_msg("PRIVMSG #chan :msg1")
        mock_msg2 = irc_msg("PRIVMSG #chan :msg2")
        self.client.msgBuff = [mock_msg1, mock_msg2]
        
        msg = self.client.getmsg()
        self.assertIs(msg, mock_msg1)
        self.assertEqual(len(self.client.msgBuff), 1)
        self.assertIs(self.client.msgBuff[0], mock_msg2)

        msg = self.client.getmsg()
        self.assertIs(msg, mock_msg2)
        self.assertEqual(len(self.client.msgBuff), 0)

    def test_getmsg_from_socket_normal_message(self):
        raw_line = f":SomeUser!~u@h PRIVMSG {TEST_NICK} :Hello there"
        self.mock_getline.return_value = raw_line
        
        msg = self.client.getmsg()
        
        self.mock_getline.assert_called_once_with(self.client.sock)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.raw, raw_line)
        self.assertEqual(msg.by, "SomeUser")
        self.assertEqual(msg.msg, "Hello there")
        self.assertEqual(len(self.client.msgBuff), 0) # Should not be buffered if fresh=False and read directly

    def test_getmsg_from_socket_ping_response(self):
        ping_line = f"PING :{TEST_SERVER}"
        # After PING, getmsg should fetch the next line for the actual return
        next_line = f":OtherUser!a@b PRIVMSG {TEST_NICK} :After PING"
        self.mock_getline.side_effect = [ping_line, next_line]
        
        msg = self.client.getmsg()
        
        self.mock_socket_instance.send.assert_any_call(f"PONG :{TEST_SERVER}\r\n".encode("utf-8"))
        self.assertIsNotNone(msg)
        self.assertEqual(msg.raw, next_line) # Ensures it returns the message after PING
        self.assertEqual(self.mock_getline.call_count, 2)

    def test_getmsg_from_socket_ctcp_version_response(self):
        ctcp_version_line = f":Querier!q@h PRIVMSG {TEST_NICK} :\x01VERSION\x01"
        next_line = f":OtherUser!a@b PRIVMSG {TEST_NICK} :After CTCP VERSION"
        self.mock_getline.side_effect = [ctcp_version_line, next_line]
        
        # Mock the sendVer method to check if it's called, or check sock.send directly
        self.client.sendVer = Mock()

        msg = self.client.getmsg()
        
        self.client.sendVer.assert_called_once_with("Querier")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.raw, next_line)
        self.assertEqual(self.mock_getline.call_count, 2)

    def test_getmsg_motd_accumulation(self):
        motd_start_line = f":{TEST_SERVER} {irc_codes.RPL_MOTDSTART} {TEST_NICK} :- Server MOTD -"
        motd_line1 = f":{TEST_SERVER} {irc_codes.RPL_MOTD} {TEST_NICK} :- Line 1 of MOTD"
        motd_line2 = f":{TEST_SERVER} {irc_codes.RPL_MOTD} {TEST_NICK} :- Line 2 of MOTD"
        motd_end_line = f":{TEST_SERVER} {irc_codes.RPL_ENDOFMOTD} {TEST_NICK} :End of MOTD"
        # Message after MOTD processing
        final_msg_line = f":User!u@h PRIVMSG {TEST_NICK} :Actual message"

        self.mock_getline.side_effect = [motd_start_line, motd_line1, motd_line2, motd_end_line, final_msg_line]
        
        # Clear any existing MOTD from client init if server was provided
        self.client.motd = []

        msg = self.client.getmsg() # This call will process all MOTD lines internally

        self.assertEqual(len(self.client.motd), 4) # Start, 2 lines, End
        self.assertIn(motd_start_line, self.client.motd)
        self.assertIn(motd_line1, self.client.motd)
        self.assertIn(motd_line2, self.client.motd)
        self.assertIn(motd_end_line, self.client.motd)
        
        self.assertIsNotNone(msg)
        self.assertEqual(msg.raw, final_msg_line) # Should return the first non-MOTD message
        self.assertEqual(self.mock_getline.call_count, 5)

    def test_getmsg_fresh_true_bypasses_buffer(self):
        buffered_msg_obj = irc_msg(f":User1!u@h PRIVMSG {TEST_NICK} :Buffered Message")
        self.client.msgBuff = [buffered_msg_obj]
        
        socket_msg_line = f":User2!u@h PRIVMSG {TEST_NICK} :Fresh Socket Message"
        self.mock_getline.return_value = socket_msg_line

        msg = self.client.getmsg(fresh=True)

        self.mock_getline.assert_called_once_with(self.client.sock)
        self.assertEqual(msg.raw, socket_msg_line)
        self.assertEqual(len(self.client.msgBuff), 1) # Buffer remains untouched
        self.assertIs(self.client.msgBuff[0], buffered_msg_obj)

    def test_getmsg_nick_collision_err_nicknameinuse(self):
        # ERR_NICKNAMEINUSE (433)
        # Client should try appending "_" to nick.
        nick_in_use_line = f":{TEST_SERVER} {irc_codes.ERR_NICKNAMEINUSE} * {TEST_NICK} :Nickname is already in use."
        next_msg_line = f":User!u@h PRIVMSG {TEST_NICK}_ :Hi new nick" # Note the underscore
        self.mock_getline.side_effect = [nick_in_use_line, next_msg_line]
        
        # Store original nick
        original_nick = self.client.nick
        
        msg_obj = self.client.getmsg() # This should trigger nick change logic

        new_nick = original_nick + "_"
        self.mock_socket_instance.send.assert_any_call(f"NICK {new_nick}\r\n".encode("utf-8"))
        self.assertEqual(self.client.current_nick, new_nick)
        self.assertEqual(msg_obj.raw, next_msg_line)

    def test_getmsg_nick_collision_rpl_nickcollision(self):
        # RPL_NICKCOLLISION (436) - some servers use this instead of 433
        nick_collision_line = f":{TEST_SERVER} {irc_codes.RPL_NICKCOLLISION} {TEST_NICK} {TEST_NICK} :Nickname collision KILL"
        next_msg_line = f":User!u@h PRIVMSG {TEST_NICK}_ :Hi new nick again"
        self.mock_getline.side_effect = [nick_collision_line, next_msg_line]
        
        original_nick = self.client.nick
        
        msg_obj = self.client.getmsg()

        new_nick = original_nick + "_"
        self.mock_socket_instance.send.assert_any_call(f"NICK {new_nick}\r\n".encode("utf-8"))
        self.assertEqual(self.client.current_nick, new_nick)
        self.assertEqual(msg_obj.raw, next_msg_line)

    def test_getmsg_nickserv_identify_prompt(self):
        # Example NickServ message prompting for identification
        # This is a specific case that pyic.py handles by sending IDENTIFY
        nickserv_notice = f":NickServ!NickServ@services. NOTICE {self.client.current_nick} :This nickname is registered. Please choose a different nickname, or identify via /msg NickServ IDENTIFY <password>."
        next_msg_line = f":User!u@h PRIVMSG {self.client.current_nick} :Post NickServ interaction"
        self.mock_getline.side_effect = [nickserv_notice, next_msg_line]
        
        # Assume client has a password set
        self.client.passwd = TEST_NICKSERV_PASS 
        
        msg_obj = self.client.getmsg()
        
        expected_identify_cmd = f"PRIVMSG NickServ :IDENTIFY {TEST_NICKSERV_PASS}\r\n".encode("utf-8")
        self.mock_socket_instance.send.assert_any_call(expected_identify_cmd)
        self.assertEqual(msg_obj.raw, next_msg_line)

    def test_getmsg_nickserv_identified_confirmation(self):
        # Example NickServ message confirming identification
        # This case in pyic.py sets self.identified = True
        nickserv_ident_confirm = f":NickServ!NickServ@services. NOTICE {self.client.current_nick} :You are now identified."
        next_msg_line = f":User!u@h PRIVMSG {self.client.current_nick} :After identification"
        self.mock_getline.side_effect = [nickserv_ident_confirm, next_msg_line]

        self.client.identified = False # Ensure it's False before the message
        msg_obj = self.client.getmsg()
        
        self.assertTrue(self.client.identified)
        self.assertEqual(msg_obj.raw, next_msg_line)


class TestIrcClientSimpleCommands(TestIrcClientBase):
    def setUp(self):
        super().setUp()
        self.client = irc_client(nick=TEST_NICK, server=None) # No auto-connect
        self.client.sock = self.mock_socket_instance
        self.client.connected = True
        self.client.current_nick = TEST_NICK

    def _assert_send(self, expected_cmd_str):
        self.mock_socket_instance.send.assert_called_once_with(expected_cmd_str.encode("utf-8"))

    def test_set_chanmode(self):
        self.client.set_chanmode(TEST_CHANNEL, "+m")
        self._assert_send(f"MODE {TEST_CHANNEL} +m\r\n")

    def test_set_mode(self):
        self.client.set_mode(TEST_NICK, "+i")
        self._assert_send(f"MODE {TEST_NICK} +i\r\n")

    def test_ping_server(self): # Method name is 'ping' in pyic.py
        self.client.ping(TEST_SERVER)
        self._assert_send(f"PING :{TEST_SERVER}\r\n")

    def test_send_whois(self):
        target_nick = "AnotherNick"
        self.client.send_whois(target_nick)
        self._assert_send(f"WHOIS {target_nick}\r\n")

    def test_set_topic(self):
        new_topic = "This is a new topic"
        self.client.set_topic(TEST_CHANNEL, new_topic)
        self._assert_send(f"TOPIC {TEST_CHANNEL} :{new_topic}\r\n")

    def test_retr_topic(self): # retrieve topic
        self.client.retr_topic(TEST_CHANNEL)
        self._assert_send(f"TOPIC {TEST_CHANNEL}\r\n")

    def test_invite(self):
        invited_nick = "FriendNick"
        self.client.invite(invited_nick, TEST_CHANNEL)
        self._assert_send(f"INVITE {invited_nick} {TEST_CHANNEL}\r\n")

    def test_kick(self):
        kicked_nick = "BadUser"
        reason = "Being disruptive"
        self.client.kick(TEST_CHANNEL, kicked_nick, reason)
        self._assert_send(f"KICK {TEST_CHANNEL} {kicked_nick} :{reason}\r\n")

    def test_kick_no_reason(self):
        kicked_nick = "AnotherBadUser"
        self.client.kick(TEST_CHANNEL, kicked_nick) # Reason is optional
        self._assert_send(f"KICK {TEST_CHANNEL} {kicked_nick}\r\n")

    def test_quit_channel(self): # Method name is 'part' in pyic.py for PART command
        reason = "Leaving for now"
        self.client.part(TEST_CHANNEL, reason)
        self._assert_send(f"PART {TEST_CHANNEL} :{reason}\r\n")

    def test_quit_channel_no_reason(self):
        self.client.part(TEST_CHANNEL)
        self._assert_send(f"PART {TEST_CHANNEL}\r\n")

    def test_quit_server(self): # Method name is 'quit' in pyic.py
        reason = "Client closing"
        self.client.quit(reason)
        self._assert_send(f"QUIT :{reason}\r\n")
        self.assertFalse(self.client.connected) # Quit should set connected to False
        self.mock_socket_instance.close.assert_called_once()

    def test_quit_server_no_reason(self):
        self.client.quit()
        self._assert_send(f"QUIT\r\n")
        self.assertFalse(self.client.connected)
        self.mock_socket_instance.close.assert_called_once()

    def test_join_channel(self): # Method name is 'join' in pyic.py
        self.client.join(TEST_CHANNEL)
        self._assert_send(f"JOIN {TEST_CHANNEL}\r\n")

    def test_join_channel_with_key(self):
        key = "secretkey"
        self.client.join(TEST_CHANNEL, key)
        self._assert_send(f"JOIN {TEST_CHANNEL} {key}\r\n")

    def test_change_nick(self):
        new_nick = "NewNickName"
        self.client.change_nick(new_nick)
        self._assert_send(f"NICK {new_nick}\r\n")
        # current_nick is updated by getmsg when server confirms, not directly by change_nick cmd
        # self.assertEqual(self.client.current_nick, new_nick) # This will be tested with getmsg logic

    def test_refresh_motd(self):
        self.client.refresh_motd()
        self._assert_send("MOTD\r\n")

    def test_sendmsg(self):
        target = "#somechannel"
        message = "Hello everyone!"
        self.client.sendmsg(target, message)
        self._assert_send(f"PRIVMSG {target} :{message}\r\n")

    def test_notice(self):
        target = "SpecificUser"
        message = "This is a private notice."
        self.client.notice(target, message)
        self._assert_send(f"NOTICE {target} :{message}\r\n")

    def test_pong_explicit_call(self): # pong() is also called by getmsg on PING
        server_token = "token12345"
        self.client.pong(server_token)
        self._assert_send(f"PONG :{server_token}\r\n")

    def test_sendver_explicit_call(self): # sendVer() is also called by getmsg on VERSION CTCP
        target_nick = "QuerierNick"
        # Assuming self.client.version is set or default
        self.client.version = "MyPyClient v0.1"
        expected_ctcp_reply = f"NOTICE {target_nick} :\x01VERSION {self.client.version}\x01\r\n"
        self.client.sendVer(target_nick)
        self._assert_send(expected_ctcp_reply)


class TestIrcClientResponseProcessingCommands(TestIrcClientBase):
    def setUp(self):
        super().setUp()
        self.client = irc_client(nick=TEST_NICK, server=None) # No auto-connect
        self.client.sock = self.mock_socket_instance # Mocked socket
        self.client.connected = True
        self.client.current_nick = TEST_NICK
        # Replace getmsg with a mock for these tests to control server responses directly
        self.client.getmsg = Mock()

    def test_get_motd(self):
        # get_motd() in pyic.py calls self.refresh_motd() then relies on self.motd being populated
        # by getmsg() calls (which are now mocked).
        # So, we simulate that self.motd is already populated.
        expected_motd_lines = [
            f":{TEST_SERVER} {irc_codes.RPL_MOTDSTART} {TEST_NICK} :- Server MOTD -",
            f":{TEST_SERVER} {irc_codes.RPL_MOTD} {TEST_NICK} :- Line 1",
            f":{TEST_SERVER} {irc_codes.RPL_ENDOFMOTD} {TEST_NICK} :End of MOTD",
        ]
        self.client.motd = list(expected_motd_lines) # Simulate MOTD has been received

        motd_string = self.client.get_motd()

        # self.mock_socket_instance.send.assert_called_once_with("MOTD\r\n".encode("utf-8")) # refresh_motd call
        # The above check is for refresh_motd, get_motd itself doesn't send.
        # The current get_motd method just returns '\n'.join(self.motd).
        self.assertEqual(motd_string, "\n".join(expected_motd_lines))

    def test_whois_success(self):
        target_nick = "TargetUser"
        whois_data_lines = [
            irc_msg(f":{TEST_SERVER} {irc_codes.RPL_WHOISUSER} {TEST_NICK} {target_nick} user host * :Real Name"),
            irc_msg(f":{TEST_SERVER} {irc_codes.RPL_WHOISSERVER} {TEST_NICK} {target_nick} server.name :Server Info"),
            irc_msg(f":{TEST_SERVER} {irc_codes.RPL_WHOISCHANNELS} {TEST_NICK} {target_nick} :@#channel1 #channel2"),
            irc_msg(f":{TEST_SERVER} {irc_codes.RPL_ENDOFWHOIS} {TEST_NICK} {target_nick} :End of WHOIS list"),
        ]
        self.client.getmsg.side_effect = whois_data_lines
        
        # whois() sends WHOIS command then processes replies via collect_who_data
        # collect_who_data uses getmsg(True)
        whois_result = self.client.whois(target_nick)

        self.mock_socket_instance.send.assert_called_once_with(f"WHOIS {target_nick}\r\n".encode("utf-8"))
        self.assertEqual(self.client.getmsg.call_count, len(whois_data_lines))
        
        self.assertIn("user", whois_result)
        self.assertEqual(whois_result["user"], f"{target_nick} user host * :Real Name")
        self.assertIn("server", whois_result)
        self.assertEqual(whois_result["server"], f"{target_nick} server.name :Server Info")
        self.assertIn("channels", whois_result)
        self.assertEqual(whois_result["channels"], f"{target_nick} :@#channel1 #channel2 #anotherchan")
        self.assertIn("idle", whois_result)
        self.assertEqual(whois_result["idle"], f"{target_nick} 12345 67890 :seconds idle, signon time")
        self.assertIn("away", whois_result)
        self.assertEqual(whois_result["away"], f"{target_nick} :Gone fishing")
        self.assertIn("operator", whois_result)
        self.assertEqual(whois_result["operator"], f"{target_nick} :is an IRC Operator")
        self.assertIn("actually", whois_result) # Parsed as 'host' in collect_who_data
        self.assertEqual(whois_result["actually"], f"{target_nick} user2@actual.host :Actual user@host")

        self.assertIn("raw", whois_result)
        # raw should contain all lines except RPL_ENDOFWHOIS
        self.assertEqual(len(whois_result["raw"]), len(whois_data_lines) - 1)

    def test_whois_no_such_nick(self):
        target_nick = "NoSuchUser"
        error_reply = irc_msg(f":{TEST_SERVER} {irc_codes.ERR_NOSUCHNICK} {TEST_NICK} {target_nick} :No such nick/channel")
        # RPL_ENDOFWHOIS also terminates the loop. Some servers send NOSUCHNICK then ENDOFWHOIS.
        end_reply = irc_msg(f":{TEST_SERVER} {irc_codes.RPL_ENDOFWHOIS} {TEST_NICK} {target_nick} :End of WHOIS list")
        self.client.getmsg.side_effect = [error_reply, end_reply]

        whois_result = self.client.whois(target_nick)

        self.mock_socket_instance.send.assert_called_once_with(f"WHOIS {target_nick}\r\n".encode("utf-8"))
        self.assertIn("error", whois_result)
        self.assertEqual(whois_result["error"], f"{target_nick} :No such nick/channel")
        self.assertNotIn("user", whois_result) # Should not have user data

    def test_get_topic_success_rpl_topic(self):
        self.client.getmsg.return_value = irc_msg(f":{TEST_SERVER} {irc_codes.RPL_TOPIC} {TEST_NICK} {TEST_CHANNEL} :This is the topic")
        
        topic = self.client.get_topic(TEST_CHANNEL)
        
        self.mock_socket_instance.send.assert_called_once_with(f"TOPIC {TEST_CHANNEL}\r\n".encode("utf-8"))
        self.client.getmsg.assert_called_once_with(True) # get_topic calls getmsg(True)
        self.assertEqual(topic, "This is the topic")

    def test_get_topic_success_rpl_notopic(self):
        self.client.getmsg.return_value = irc_msg(f":{TEST_SERVER} {irc_codes.RPL_NOTOPIC} {TEST_NICK} {TEST_CHANNEL} :No topic is set")
        
        topic = self.client.get_topic(TEST_CHANNEL)
        
        self.mock_socket_instance.send.assert_called_once_with(f"TOPIC {TEST_CHANNEL}\r\n".encode("utf-8"))
        self.client.getmsg.assert_called_once_with(True)
        self.assertEqual(topic, "No topic is set") # RPL_NOTOPIC's message is returned

    def test_get_topic_other_message_received(self):
        # If a non-topic related message is received after sending TOPIC command
        self.client.getmsg.return_value = irc_msg(f":SomeUser!u@h PRIVMSG {TEST_CHANNEL} :Some other message")
        
        topic = self.client.get_topic(TEST_CHANNEL)
        
        self.mock_socket_instance.send.assert_called_once_with(f"TOPIC {TEST_CHANNEL}\r\n".encode("utf-8"))
        self.client.getmsg.assert_called_once_with(True)
        self.assertIsNone(topic) # Or some other indicator of not receiving a topic reply

    def test_whowas_success(self):
        target_nick = "OldUser"
        limit = 5
        whowas_data = [
            irc_msg(f":{TEST_SERVER} {irc_codes.RPL_WHOWASUSER} {TEST_NICK} {target_nick} user host * :Real Name Was"),
            irc_msg(f":{TEST_SERVER} {irc_codes.RPL_ENDOFWHOWAS} {TEST_NICK} {target_nick} :End of WHOWAS"),
        ]
        self.client.getmsg.side_effect = whowas_data

        result = self.client.whowas(target_nick, limit)

        self.mock_socket_instance.send.assert_called_once_with(f"WHOWAS {target_nick} {limit}\r\n".encode("utf-8"))
        self.assertIn("user", result) # collect_who_data structure
        self.assertEqual(result["user"], f"{target_nick} user host * :Real Name Was")

    def test_get_users_in_channel(self):
        # RPL_NAMREPLY (353) and RPL_ENDOFNAMES (366)
        namreply_1 = f":{TEST_SERVER} {irc_codes.RPL_NAMREPLY} {TEST_NICK} = {TEST_CHANNEL} :@{TEST_NICK} User1 +User2"
        namreply_2 = f":{TEST_SERVER} {irc_codes.RPL_NAMREPLY} {TEST_NICK} = {TEST_CHANNEL} :User3 User4 @AnotherOp"
        endofnames = f":{TEST_SERVER} {irc_codes.RPL_ENDOFNAMES} {TEST_NICK} {TEST_CHANNEL} :End of /NAMES list."
        
        self.client.getmsg.side_effect = [
            irc_msg(namreply_1),
            irc_msg(namreply_2),
            irc_msg(endofnames)
        ]
        
        users = self.client.get_users(TEST_CHANNEL)
        
        self.mock_socket_instance.send.assert_called_once_with(f"NAMES {TEST_CHANNEL}\r\n".encode("utf-8"))
        self.assertEqual(self.client.getmsg.call_count, 3)
        
        expected_users = ["@TestNick", "User1", "+User2", "User3", "User4", "@AnotherOp"]
        self.assertListEqual(sorted(users), sorted(expected_users))

    def test_get_channels(self):
        # RPL_LISTSTART (321), RPL_LIST (322), RPL_LISTEND (323)
        list_start = f":{TEST_SERVER} {irc_codes.RPL_LISTSTART} {TEST_NICK} Channel :Users Name" # Some servers omit this
        list_item1 = f":{TEST_SERVER} {irc_codes.RPL_LIST} {TEST_NICK} #channel1 10 :Topic for channel1"
        list_item2 = f":{TEST_SERVER} {irc_codes.RPL_LIST} {TEST_NICK} #channel2 5 :Another topic here"
        list_end = f":{TEST_SERVER} {irc_codes.RPL_LISTEND} {TEST_NICK} :End of /LIST"

        self.client.getmsg.side_effect = [
            #irc_msg(list_start), # Optional, pyic.py might not require it
            irc_msg(list_item1),
            irc_msg(list_item2),
            irc_msg(list_end)
        ]

        channels = self.client.get_channels()

        self.mock_socket_instance.send.assert_called_once_with("LIST\r\n".encode("utf-8"))
        # Call count depends on whether LISTSTART is processed or skipped by getmsg loop
        # Assuming getmsg processes these three relevant lines:
        self.assertEqual(self.client.getmsg.call_count, 3) 

        expected_channels = {
            "#channel1": {"users": "10", "topic": "Topic for channel1"},
            "#channel2": {"users": "5", "topic": "Another topic here"},
        }
        self.assertDictEqual(channels, expected_channels)


if __name__ == '__main__':
    unittest.main()
