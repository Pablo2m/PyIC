import unittest
import sys # To set the exit code

if __name__ == '__main__':
    # Create a TestLoader instance
    loader = unittest.TestLoader()

    # Discover tests in the 'tests' directory
    # Tests should be in files named 'test_*.py'
    suite = loader.discover('tests', pattern='test_*.py')

    # Create a TextTestRunner instance
    # verbosity=2 provides more detailed output
    runner = unittest.TextTestRunner(verbosity=2)

    # Run the tests
    result = runner.run(suite)

    # Exit with an appropriate status code
    if result.wasSuccessful():
        sys.exit(0)
    else:
        sys.exit(1)
