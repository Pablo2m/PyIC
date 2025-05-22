import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import time # For optimistic message timestamp

# Adjust path to import RioIrcClientApp and IRCManager
# Assumes test_main_app.py is in the rio_irc_client directory.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


# Attempt to import the application components
try:
    from main import RioIrcClientApp
    # IRCManager might be imported by main.py, or we might need to mock its path too.
    # For these tests, we're patching 'main.IRCManager' so the actual import path of IRCManager
    # for main.py is what matters.
except ImportError as e:
    # This block is for diagnostics if the test environment has trouble finding main.py
    # It's not expected to be hit if the sys.path manipulation above is correct
    # and the test is run from the project root or similar.
    print(f"PYTHONPATH: {os.environ.get('PYTHONPATH')}")
    print(f"CWD: {os.getcwd()}")
    print(f"sys.path: {sys.path}")
    print(f"Error importing app components in test_main_app.py: {e}. Ensure tests are run correctly.")
    # Re-raise or define a placeholder to avoid subsequent errors if critical
    raise


# Mock rio.App.call_soon_threadsafe to run the target method immediately and synchronously
def immediate_call_soon_threadsafe(self, callback, *args):
    callback(*args)

@patch('main.rio.App.call_soon_threadsafe', new=immediate_call_soon_threadsafe)
class TestRioIrcClientApp(unittest.TestCase):

    @patch('main.IRCManager') # Mock IRCManager as it's seen by main.py
    def setUp(self, MockIRCManager):
        self.mock_irc_manager_instance = MockIRCManager.return_value
        self.mock_irc_manager_instance.is_connected = False # Default mock state

        # Rio's App instantiation might need to be within a session context
        # For now, we assume it can be instantiated directly for these logic tests.
        # The call_soon_threadsafe mock above helps simplify testing async UI updates.
        self.app = RioIrcClientApp()
        # Ensure the app instance uses our specific mock instance
        self.app.irc_manager = self.mock_irc_manager_instance


    def test_app_initialization(self):
        self.assertEqual(self.app.connection_status, "Disconnected")
        self.assertEqual(self.app.server_address, "irc.libera.chat") # Default from app
        self.assertEqual(self.app.nickname, "RioIRCUser") # Default from app
        self.assertEqual(self.app.chat_messages, [])

    def test_event_privmsg_to_channel(self):
        event = {'type': 'PRIVMSG', 'by': 'UserA', 'to': '#channel1', 'message': 'Hello world!'}
        self.app.current_channel = '#channel1' # Viewing this channel
        self.app._process_irc_event_in_main_thread(event) # Directly call for test
        
        self.assertEqual(len(self.app.chat_messages), 1)
        last_msg = self.app.chat_messages[0]
        self.assertEqual(last_msg['sender'], 'UserA')
        self.assertEqual(last_msg['text'], 'Hello world!')
        self.assertEqual(last_msg['channel'], '#channel1')

    def test_event_privmsg_to_self_nick(self):
        self.app.nickname = "MyNick" # Set the app's current nickname state
        event = {'type': 'PRIVMSG', 'by': 'UserB', 'to': 'MyNick', 'message': 'Private Hullo!'}
        # When receiving a PM, current_channel might be something else,
        # but the message should be associated with 'UserB' as context.
        self.app._process_irc_event_in_main_thread(event)
        
        self.assertEqual(len(self.app.chat_messages), 1)
        last_msg = self.app.chat_messages[0]
        self.assertEqual(last_msg['sender'], 'UserB')
        self.assertEqual(last_msg['text'], 'Private Hullo!')
        self.assertEqual(last_msg['channel'], 'userb') # PMs are channelized by sender's nick (lowercased)


    def test_event_join_self_and_namreply(self):
        self.app.nickname = "TestNick"
        join_event = {'type': 'JOIN', 'by': 'TestNick', 'to': '#newchannel', 'message': '#newchannel'}
        self.app._process_irc_event_in_main_thread(join_event)
        
        self.assertIn('#newchannel', self.app.active_channels)
        self.assertEqual(self.app.current_channel, '#newchannel')
        self.mock_irc_manager_instance.send_raw_command.assert_called_with("NAMES #newchannel")

        # Simulate NAMES reply
        # Adjusted 'to' to reflect what irc_msg.py would likely produce for RPL_NAMREPLY's 'to' field (target of numeric)
        # and include 'params' as main.py uses it for NAMREPLY and ENDOFNAMES
        nam_event = {
            'type': 'RPL_NAMREPLY', 'raw':':server 353 TestNick = #newchannel :User1 @User2 TestNick',
            'to': 'TestNick', 'params': ['TestNick', '=', '#newchannel'], 
            'message': 'User1 @User2 TestNick' # Message is just the names part after colon
        }
        self.app._process_irc_event_in_main_thread(nam_event)
        
        end_names_event = {
            'type': 'RPL_ENDOFNAMES', 'raw':':server 366 TestNick #newchannel :End of /NAMES list.',
            'to': 'TestNick', 'params': ['TestNick', '#newchannel'], 
            'message': 'End of /NAMES list.'
        }
        self.app._process_irc_event_in_main_thread(end_names_event)
        
        self.assertCountEqual(self.app.user_list, ['User1', 'User2', 'TestNick'])

    def test_do_connect_disconnect_actions(self):
        # Test connect
        self.mock_irc_manager_instance.is_connected = False
        self.app.server_address = "irc.example.com"
        self.app.server_port = "6667"
        self.app.nickname = "ConnectTest"
        self.app.channel_to_join = "#connect"
        
        self.app.do_connect_disconnect()
        self.mock_irc_manager_instance.connect.assert_called_with(
            nick="ConnectTest", server="irc.example.com", port=6667, 
            channels=["#connect"], ssl_conn=False
        )
        self.assertEqual(self.app.chat_messages, []) # Ensure logs cleared

        # Test disconnect
        self.mock_irc_manager_instance.is_connected = True # Simulate connected state
        self.app.do_connect_disconnect()
        self.mock_irc_manager_instance.disconnect.assert_called_once()

    def test_do_send_ui_message(self):
        self.mock_irc_manager_instance.is_connected = True
        self.app.current_channel = "#chat"
        self.app.message_input = "A test message"
        self.app.nickname = "MySelf" # For optimistic display
        
        self.app.do_send_ui_message()
        
        self.mock_irc_manager_instance.send_channel_message.assert_called_with("#chat", "A test message")
        self.assertEqual(self.app.message_input, "")
        self.assertEqual(len(self.app.chat_messages), 1)
        self.assertEqual(self.app.chat_messages[0]['text'], "A test message")
        self.assertEqual(self.app.chat_messages[0]['sender'], "MySelf")

    def test_select_channel(self):
        self.mock_irc_manager_instance.is_connected = True
        self.app.active_channels = ["#general", "#fun"]
        self.app.current_channel = "#general"
        
        self.app.select_channel("#fun")
        
        self.assertEqual(self.app.current_channel, "#fun")
        self.assertEqual(self.app.user_list, []) # Cleared
        self.mock_irc_manager_instance.send_raw_command.assert_called_with("NAMES #fun")
        
    def test_kick_event_self_kicked(self):
        self.app.nickname = "MyKickedNick"
        self.app.active_channels = ["#channel1", "#channel2"]
        self.app.current_channel = "#channel1"
        
        # pyic.py's irc_msg sets `msg.by` to kicker, `msg.to` to channel, 
        # `msg.kicked` (from params[1]) to who was kicked, `msg.msg` to reason.
        # The _process_irc_event_in_main_thread expects 'kicked' field in event_data.
        kick_event = {
            'type': 'KICK', 
            'by': 'Operator',       
            'kicked': 'MyKickedNick', # This should be the one checked
            'to': '#channel1',      
            'message': 'Reason for kick' 
        }
        self.app._process_irc_event_in_main_thread(kick_event)
        
        self.assertNotIn("#channel1", self.app.active_channels)
        self.assertEqual(self.app.current_channel, "#channel2") # Falls back to next active
        self.assertTrue(any("MyKickedNick was kicked from #channel1" in msg['text'] for msg in self.app.chat_messages))
        self.assertEqual(self.app.connection_status, "You were kicked from #channel1 by Operator.") # Updated assertion

    def test_kick_event_other_kicked(self):
        self.app.current_channel = "#channel1"
        self.app.user_list = ["UserA", "UserToKick", "UserC"]
        
        kick_event = {
            'type': 'KICK', 
            'by': 'Operator', 
            'kicked': 'UserToKick', 
            'to': '#channel1', 
            'message': 'Reason'
        }
        self.app._process_irc_event_in_main_thread(kick_event)
        
        self.assertNotIn("UserToKick", self.app.user_list)
        self.assertIn("UserA", self.app.user_list)
        self.assertTrue(any("UserToKick was kicked from #channel1" in msg['text'] for msg in self.app.chat_messages))

    def test_do_send_ui_message_with_slash_commands(self):
        self.mock_irc_manager_instance.is_connected = True
        self.app.current_channel = "#testchannel"
        
        commands_to_test = [
            "/me dances",
            "/nick NewShinyNick",
            "/whois SomeOtherUser"
        ]
        
        for cmd in commands_to_test:
            self.mock_irc_manager_instance.process_input.reset_mock() # Reset before each call
            self.app.message_input = cmd
            self.app.do_send_ui_message()
            # process_input is called on the app's irc_manager instance, which is our mock
            self.mock_irc_manager_instance.process_input.assert_called_with("#testchannel", cmd)

    def test_event_self_action_display(self):
        self.app.nickname = "MyOwnNick" # Ensure app's nickname state is set
        event = {'type': 'SELF_ACTION', 'by': 'MyOwnNick', 'to': '#general', 'message': 'is doing a self action'}
        self.app._process_irc_event_in_main_thread(event)
        
        self.assertEqual(len(self.app.chat_messages), 1)
        last_msg = self.app.chat_messages[0]
        self.assertEqual(last_msg['text'], '* MyOwnNick is doing a self action')
        self.assertTrue(last_msg.get('is_action'))
        self.assertEqual(last_msg['channel'], '#general')

    def test_whois_data_aggregation_and_display(self):
        # Simulate starting a WHOIS query
        # In the actual app, this is triggered by IRCManager's status message after /whois
        self.app.whois_query_nick = "TargetUser"
        self.app.current_whois_data = {'nick': "TargetUser"}
        self.app.current_channel = "#current" # Context for logging

        # RPL_WHOISUSER (311)
        # pyic params: [<nick>, <user>, <host>, <*>] Message: <real_name>
        event_user = {'type': '311', 'params': ['TargetUser', 't_user', 't_host', '*'], 'message': 'Real Name Is This'}
        self.app._process_irc_event_in_main_thread(event_user)
        self.assertEqual(self.app.current_whois_data.get('real_name'), 'Real Name Is This')
        self.assertEqual(self.app.current_whois_data.get('user'), 't_user')
        self.assertEqual(self.app.current_whois_data.get('host'), 't_host')


        # RPL_WHOISCHANNELS (319)
        # pyic params: [<nick>] Message: <channel_list e.g., "@#chan1 #chan2">
        event_channels = {'type': '319', 'params': ['TargetUser'], 'message': '@#channel1 #channel2'}
        self.app._process_irc_event_in_main_thread(event_channels)
        self.assertIn('@#channel1', self.app.current_whois_data.get('channels', []))
        self.assertIn('#channel2', self.app.current_whois_data.get('channels', []))

        # RPL_ENDOFWHOIS (318)
        # pyic params: [<nick>] Message: <text like "End of /WHOIS list.">
        event_end = {'type': '318', 'params': ['TargetUser'], 'message': 'End of /WHOIS list.'}
        initial_msg_count = len(self.app.chat_messages)
        self.app._process_irc_event_in_main_thread(event_end)
        
        # Check that chat_messages contains WHOIS summary
        self.assertTrue(len(self.app.chat_messages) > initial_msg_count + 2) # At least title, one data line, end line
        
        # Consolidate chat messages for checking
        logged_whois_info = "\n".join([msg['text'] for msg in self.app.chat_messages[initial_msg_count:]])
        
        self.assertIn("--- WHOIS results for TargetUser ---", logged_whois_info)
        self.assertIn("Nick: TargetUser", logged_whois_info)
        self.assertIn("Real Name: Real Name Is This", logged_whois_info)
        self.assertIn("User: t_user@t_host", logged_whois_info)
        self.assertIn("Channels: @#channel1 #channel2", logged_whois_info)
        self.assertIn("--- End of WHOIS ---", logged_whois_info)
        
        self.assertIsNone(self.app.whois_query_nick)
        self.assertEqual(self.app.current_whois_data, {})

    def test_whois_error_no_such_nick(self):
        self.app.whois_query_nick = "NonExistent"
        self.app.current_whois_data = {'nick': "NonExistent"}
        self.app.current_channel = "#chat"

        # ERR_NOSUCHNICK (401)
        # pyic params: [<queried_nick_attempt>] Message: <error_message>
        event_error = {'type': '401', 'params': ['NonExistent'], 'message': 'No such nick/channel'}
        initial_msg_count = len(self.app.chat_messages)
        self.app._process_irc_event_in_main_thread(event_error)

        self.assertTrue(len(self.app.chat_messages) > initial_msg_count)
        last_msg = self.app.chat_messages[-1] # Assuming error is the last message added
        self.assertTrue(last_msg.get('is_error'))
        self.assertIn("WHOIS Error for NonExistent: No such nick/channel", last_msg['text'])
        
        self.assertIsNone(self.app.whois_query_nick)
        self.assertEqual(self.app.current_whois_data, {})

if __name__ == '__main__':
    # This allows running the tests directly from this file.
    unittest.main()
