import unittest
from unittest.mock import patch, mock_open
import socket # Used for ntop and dcc_download tests

# Assuming dcc.py is in the parent directory or PYTHONPATH is set up correctly
# For now, let's assume it's in the same directory for simplicity of getting started.
# Will adjust if dcc.py is located elsewhere.
try:
    from dcc import int2uint4, clean_msg, ntop, decompose_dcc_offer, dcc_download
except ImportError:
    # This is a fallback if dcc.py is in the parent directory as is common in projects
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from dcc import int2uint4, clean_msg, ntop, decompose_dcc_offer, dcc_download

class TestDCCFunctions(unittest.TestCase):
    def test_int2uint4(self):
        self.assertEqual(int2uint4(0), b'\x00\x00\x00\x00')
        self.assertEqual(int2uint4(1), b'\x00\x00\x00\x01')
        self.assertEqual(int2uint4(255), b'\x00\x00\x00\xff')
        self.assertEqual(int2uint4(256), b'\x00\x00\x01\x00')
        self.assertEqual(int2uint4(65535), b'\x00\x00\xff\xff')
        self.assertEqual(int2uint4(65536), b'\x00\x01\x00\x00')
        self.assertEqual(int2uint4(16777215), b\x00\xff\xff\xff')
        self.assertEqual(int2uint4(16777216), b'\x01\x00\x00\x00')
        self.assertEqual(int2uint4(4294967295), b'\xff\xff\xff\xff') # Max 4-byte unsigned int
        # Test with a negative number, assuming it should handle it gracefully or raise an error
        # Depending on the intended behavior of int2uint4, this might need adjustment
        # If it's supposed to convert to two's complement or raise error.
        # For now, let's assume it might wrap around or be treated as unsigned.
        # Given the name "uint", negative inputs are likely not expected or should raise error.
        # Let's assume an error for now if dcc.py doesn't specify.
        # self.assertRaises(SomeExpectedError, int2uint4, -1)

    def test_clean_msg(self):
        self.assertEqual(clean_msg("hello\x01world"), "helloworld")
        self.assertEqual(clean_msg("test\x02string\x03with\x04control\x05chars\x06\x07\x08\x09."), "teststringwithcontrolchars.")
        self.assertEqual(clean_msg("no control chars"), "no control chars")
        self.assertEqual(clean_msg(""), "")
        self.assertEqual(clean_msg("\x01\x02\x03\x04\x05\x06\x07\x08\x09"), "")
        self.assertEqual(clean_msg(" leading\x01 and trailing\x02"), " leading and trailing")

    def test_ntop(self):
        self.assertEqual(ntop(0), "0.0.0.0")
        self.assertEqual(ntop(16777216), "1.0.0.0")
        self.assertEqual(ntop(3232235521), "192.168.0.1") # Common private IP
        self.assertEqual(ntop(2130706433), "127.0.0.1")   # Loopback
        self.assertEqual(ntop(4294967295), "255.255.255.255") # Max IP
        # Test with a value that would be an invalid IP if not handled,
        # or if it expects a signed int, though ntop usually deals with unsigned.
        # self.assertRaises(SomeExpectedError, ntop, -1) # Or expected behavior for negatives

    def test_decompose_dcc_offer(self):
        # Valid SEND offer
        self.assertEqual(decompose_dcc_offer('DCC SEND "file name.txt" 192.168.0.1 1234 1024'),
                         ('SEND', 'file name.txt', '192.168.0.1', 1234, 1024, False))
        # Valid SEND offer without quotes
        self.assertEqual(decompose_dcc_offer('DCC SEND file_name.txt 192.168.0.1 1234 1024'),
                         ('SEND', 'file_name.txt', '192.168.0.1', 1234, 1024, False))
        # Valid SEND offer with path (should be stripped)
        self.assertEqual(decompose_dcc_offer('DCC SEND "/path/to/file name.txt" 192.168.0.1 1234 1024'),
                         ('SEND', 'file name.txt', '192.168.0.1', 1234, 1024, False))
        # Valid SEND offer without size
        self.assertEqual(decompose_dcc_offer('DCC SEND "file.dat" 127.0.0.1 5000'),
                         ('SEND', 'file.dat', '127.0.0.1', 5000, 0, False))

        # Valid TSEND offer
        self.assertEqual(decompose_dcc_offer('DCC TSEND "archive.zip" 10.0.0.1 6000 20480 turbo'),
                         ('SEND', 'archive.zip', '10.0.0.1', 6000, 20480, True))
        # Valid TSEND offer with different turbo keyword casing (assuming case-insensitivity for "turbo")
        self.assertEqual(decompose_dcc_offer('DCC TSEND "archive.zip" 10.0.0.1 6000 20480 TuRbO'),
                         ('SEND', 'archive.zip', '10.0.0.1', 6000, 20480, True))
        # Valid TSEND offer without size
        self.assertEqual(decompose_dcc_offer('DCC TSEND "another.file" 10.0.0.2 6001 turbo'),
                         ('SEND', 'another.file', '10.0.0.2', 6001, 0, True))

        # Malformed offers
        self.assertFalse(decompose_dcc_offer('DCC SEND "file.txt"')) # Too few args
        self.assertFalse(decompose_dcc_offer('DCC SEND "file.txt" 192.168.0.1')) # Still too few
        self.assertFalse(decompose_dcc_offer('DCC SEND "file.txt" 192.168.0.1 notaport 1024')) # Invalid port
        self.assertFalse(decompose_dcc_offer('DCC SEND "file.txt" 192.168.0.1 1234 notasize')) # Invalid size
        self.assertFalse(decompose_dcc_offer('DCC OTHER "file.txt" 192.168.0.1 1234 1024')) # Invalid type
        self.assertFalse(decompose_dcc_offer('DCC SEND file.txt 192.168.0.1.123 1234 1024')) # Invalid IP
        self.assertFalse(decompose_dcc_offer('')) # Empty string
        self.assertFalse(decompose_dcc_offer('DCC TSEND "file" 1.2.3.4 1234 5678not turbo')) # Missing space before turbo


@patch('dcc.socket.socket')
@patch('dcc.open', new_callable=mock_open)
class TestDCCDownload(unittest.TestCase):
    def setUp(self):
        # Reset mocks for each test to prevent interference
        self.mock_socket_instance = socket.socket.return_value
        self.mock_file_handle = open.return_value

    def test_dcc_download_init(self, mock_open_func, mock_socket_constructor):
        # Test basic initialization
        d = dcc_download("testfile.txt", "127.0.0.1", 1234, 1024, False)
        self.assertEqual(d.filename, "testfile.txt")
        self.assertEqual(d.host, "127.0.0.1")
        self.assertEqual(d.port, 1234)
        self.assertEqual(d.size, 1024)
        self.assertEqual(d.turbo, False)
        self.assertIsNone(d.func)
        self.assertEqual(d.total_bytes, 0)
        self.assertFalse(d.connected)

        # Test initialization with a callback function
        callback_func = lambda bytes_received, total_size: None
        d_with_func = dcc_download("another.zip", "192.168.1.1", 5000, 2048, True, func=callback_func)
        self.assertEqual(d_with_func.filename, "another.zip")
        self.assertEqual(d_with_func.host, "192.168.1.1")
        self.assertEqual(d_with_func.port, 5000)
        self.assertEqual(d_with_func.size, 2048)
        self.assertTrue(d_with_func.turbo)
        self.assertEqual(d_with_func.func, callback_func)

    def test_run_success_no_turbo(self, mock_open_func, mock_socket_constructor):
        # Setup
        mock_socket = mock_socket_constructor.return_value
        mock_file = mock_open_func.return_value
        
        file_data = b"some file data" * 100 # 1400 bytes
        file_size = len(file_data)

        # Configure socket.recv to simulate receiving data
        # Chunk size is 1024 for dcc_download
        chunks = [file_data[i:i+1024] for i in range(0, file_size, 1024)]
        if not chunks: # Handle zero size file
            chunks = [b'']
        mock_socket.recv.side_effect = chunks + [b''] # Add empty bytes at the end to stop recv loop

        callback_mock = unittest.mock.Mock()

        d = dcc_download("test.dat", "127.0.0.1", 1234, file_size, False, func=callback_mock)
        
        # Execute
        result = d.run()

        # Assert
        self.assertTrue(result)
        self.assertTrue(d.connected) # Should be True after successful connect, then False after close
        mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 1234))
        mock_open_func.assert_called_once_with("test.dat", "wb")
        
        # Check file writes
        self.assertEqual(mock_file.write.call_count, len(chunks) if file_size > 0 else 0)
        if file_size > 0:
            for i, chunk in enumerate(chunks):
                self.assertEqual(mock_file.write.call_args_list[i][0][0], chunk)

        # Check acknowledgements for non-turbo
        # Number of acks should be number of chunks received.
        # total_bytes is updated *before* ack is sent.
        expected_acks = []
        current_bytes = 0
        for chunk in chunks:
            current_bytes += len(chunk)
            if len(chunk) > 0 : # No ack for final empty recv that closes loop
                 expected_acks.append(unittest.mock.call(int2uint4(current_bytes)))
        
        self.assertEqual(mock_socket.sendall.call_count, len(expected_acks))
        self.assertEqual(mock_socket.sendall.call_args_list, expected_acks)

        # Check callback
        self.assertEqual(callback_mock.call_count, len(chunks) if file_size > 0 else 0 )
        if file_size > 0:
            current_bytes_for_cb = 0
            for i, chunk in enumerate(chunks):
                current_bytes_for_cb += len(chunk)
                self.assertEqual(callback_mock.call_args_list[i][0][0], current_bytes_for_cb)
                self.assertEqual(callback_mock.call_args_list[i][0][1], file_size)
        
        self.assertEqual(d.total_bytes, file_size)
        mock_file.close.assert_called_once()
        mock_socket.close.assert_called_once()

    def test_run_success_turbo(self, mock_open_func, mock_socket_constructor):
        # Setup
        mock_socket = mock_socket_constructor.return_value
        mock_file = mock_open_func.return_value
        
        file_data = b"turbo data stream" * 200 # 3400 bytes
        file_size = len(file_data)

        # Configure socket.recv to simulate receiving data
        chunks = [file_data[i:i+1024] for i in range(0, file_size, 1024)]
        if not chunks: chunks = [b'']
        mock_socket.recv.side_effect = chunks + [b'']

        callback_mock = unittest.mock.Mock()

        d = dcc_download("turbo.dat", "10.0.0.1", 6000, file_size, True, func=callback_mock)
        
        # Execute
        result = d.run()

        # Assert
        self.assertTrue(result)
        mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("10.0.0.1", 6000))
        mock_open_func.assert_called_once_with("turbo.dat", "wb")
        
        self.assertEqual(mock_file.write.call_count, len(chunks) if file_size > 0 else 0)
        if file_size > 0:
            for i, chunk in enumerate(chunks):
                self.assertEqual(mock_file.write.call_args_list[i][0][0], chunk)

        # Check NO acknowledgements for turbo
        mock_socket.sendall.assert_not_called()

        # Check callback
        self.assertEqual(callback_mock.call_count, len(chunks) if file_size > 0 else 0)
        if file_size > 0:
            current_bytes_for_cb = 0
            for i, chunk in enumerate(chunks):
                current_bytes_for_cb += len(chunk)
                self.assertEqual(callback_mock.call_args_list[i][0][0], current_bytes_for_cb)
                self.assertEqual(callback_mock.call_args_list[i][0][1], file_size)
        
        self.assertEqual(d.total_bytes, file_size)
        mock_file.close.assert_called_once()
        mock_socket.close.assert_called_once()

    def test_run_fail_connect(self, mock_open_func, mock_socket_constructor):
        # Setup
        mock_socket = mock_socket_constructor.return_value
        mock_socket.connect.side_effect = socket.error("Connection refused")

        d = dcc_download("fail.dat", "127.0.0.1", 1234, 100, False)
        
        # Execute
        result = d.run()

        # Assert
        self.assertFalse(result)
        self.assertFalse(d.connected)
        mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 1234))
        mock_open_func.assert_not_called() # File should not be opened if connect fails
        mock_socket.close.assert_called_once() # Socket should be closed even on connect failure

    def test_run_fail_file_open(self, mock_open_func, mock_socket_constructor):
        # Setup
        mock_socket = mock_socket_constructor.return_value
        mock_open_func.side_effect = IOError("Permission denied")

        d = dcc_download("noperm.dat", "127.0.0.1", 1234, 100, False)

        # Execute
        result = d.run()

        # Assert
        self.assertFalse(result)
        self.assertFalse(d.connected) # Should be false as connection closes after file error
        mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 1234))
        mock_open_func.assert_called_once_with("noperm.dat", "wb")
        mock_socket.close.assert_called_once() # Socket should be closed

    def test_run_fail_recv(self, mock_open_func, mock_socket_constructor):
        # Setup
        mock_socket = mock_socket_constructor.return_value
        mock_file = mock_open_func.return_value
        mock_socket.recv.side_effect = socket.error("Socket error during recv")

        d = dcc_download("recv_err.dat", "127.0.0.1", 1234, 100, False)

        # Execute
        result = d.run()

        # Assert
        self.assertFalse(result)
        mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 1234))
        mock_open_func.assert_called_once_with("recv_err.dat", "wb")
        mock_file.write.assert_not_called() # No data written if recv fails immediately
        mock_file.close.assert_called_once()
        mock_socket.close.assert_called_once()

    def test_run_partial_download_then_recv_error_no_turbo(self, mock_open_func, mock_socket_constructor):
        # Setup
        mock_socket = mock_socket_constructor.return_value
        mock_file = mock_open_func.return_value
        
        file_data_part1 = b"first part " * 10 # 110 bytes
        file_size = 1000 # Larger than part1

        mock_socket.recv.side_effect = [file_data_part1, socket.error("Network dropped")]
        callback_mock = unittest.mock.Mock()

        d = dcc_download("partial.dat", "127.0.0.1", 1234, file_size, False, func=callback_mock)
        
        # Execute
        result = d.run()

        # Assert
        self.assertFalse(result) # Should be false as download did not complete
        mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 1234))
        mock_open_func.assert_called_once_with("partial.dat", "wb")
        
        mock_file.write.assert_called_once_with(file_data_part1)
        mock_socket.sendall.assert_called_once_with(int2uint4(len(file_data_part1))) # Ack for the first part
        
        callback_mock.assert_called_once_with(len(file_data_part1), file_size)
        
        self.assertEqual(d.total_bytes, len(file_data_part1))
        mock_file.close.assert_called_once()
        mock_socket.close.assert_called_once()

    def test_run_zero_size_file(self, mock_open_func, mock_socket_constructor):
        # Setup
        mock_socket = mock_socket_constructor.return_value
        mock_file = mock_open_func.return_value
        
        # For a zero-size file, recv might be called once and return b''
        mock_socket.recv.side_effect = [b''] 
        callback_mock = unittest.mock.Mock()

        d = dcc_download("empty.dat", "127.0.0.1", 1234, 0, False, func=callback_mock)
        
        # Execute
        result = d.run()

        # Assert
        self.assertTrue(result) # Zero size file is technically a successful download
        mock_socket_constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 1234))
        mock_open_func.assert_called_once_with("empty.dat", "wb")
        
        mock_file.write.assert_not_called() # Nothing to write
        # Non-turbo still expects an ack for the 0 bytes to confirm completion,
        # but the current dcc.py code only sends ack if len(buf) > 0.
        # If d.total_bytes (which is 0) matches d.size (0), it's success.
        # No ack should be sent if recv returns b'' immediately based on current dcc.py
        mock_socket.sendall.assert_not_called()
        
        callback_mock.assert_not_called() # Callback is only called if len(buf) > 0
        
        self.assertEqual(d.total_bytes, 0)
        mock_file.close.assert_called_once()
        mock_socket.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
