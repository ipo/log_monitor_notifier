#!/usr/bin/env python3

import unittest
import tempfile
import os
import time
from log_monitor import LogMonitor


class TestLogMonitor(unittest.TestCase):
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log')
        self.temp_file.close()
        self.temp_file_path = self.temp_file.name
        # Use default patterns for backward compatibility
        self.monitor = LogMonitor([self.temp_file_path])
    
    def tearDown(self):
        if os.path.exists(self.temp_file_path):
            os.unlink(self.temp_file_path)
    
    def test_check_patterns_error(self):
        """Test that ERROR patterns are detected"""
        test_line = "2025-09-05 10:01:20 ERROR Failed to process payment"
        matches = self.monitor.check_patterns(test_line)
        self.assertIn('ERROR.*', matches)
        self.assertEqual(len(matches), 1)
    
    def test_check_patterns_critical(self):
        """Test that CRITICAL patterns are detected"""
        test_line = "2025-09-05 10:03:15 CRITICAL System memory usage at 95%"
        matches = self.monitor.check_patterns(test_line)
        self.assertIn('CRITICAL.*', matches)
        self.assertEqual(len(matches), 1)
    
    def test_check_patterns_fatal(self):
        """Test that FATAL patterns are detected"""
        test_line = "2025-09-05 10:08:00 FATAL System crash detected"
        matches = self.monitor.check_patterns(test_line)
        self.assertIn('FATAL.*', matches)
        self.assertEqual(len(matches), 1)
    
    def test_check_patterns_exception(self):
        """Test that exception patterns are detected"""
        test_line = "2025-09-05 10:05:01 ERROR Exception in thread-pool-1: NullPointerException"
        matches = self.monitor.check_patterns(test_line)
        self.assertIn('ERROR.*', matches)
        self.assertIn('exception', matches)
        self.assertEqual(len(matches), 2)
    
    def test_check_patterns_failed_login(self):
        """Test that failed login patterns are detected"""
        test_line = "2025-09-05 10:07:30 ERROR Failed login attempt for user: hacker123"
        matches = self.monitor.check_patterns(test_line)
        self.assertIn('ERROR.*', matches)
        self.assertIn('failed.*login', matches)
        self.assertEqual(len(matches), 2)
    
    def test_check_patterns_case_insensitive(self):
        """Test that patterns work case insensitively"""
        test_lines = [
            "error in system",
            "Error in system", 
            "ERROR in system",
            "ErRoR in system"
        ]
        for line in test_lines:
            with self.subTest(line=line):
                matches = self.monitor.check_patterns(line)
                self.assertIn('ERROR.*', matches)
    
    def test_check_patterns_no_match(self):
        """Test that non-matching lines return empty list"""
        test_line = "2025-09-05 10:00:01 INFO Application started successfully"
        matches = self.monitor.check_patterns(test_line)
        self.assertEqual(matches, [])
    
    def test_check_patterns_multiple_patterns(self):
        """Test that multiple patterns can match the same line"""
        test_line = "CRITICAL ERROR: Exception occurred during failed login"
        matches = self.monitor.check_patterns(test_line)
        expected_patterns = ['ERROR.*', 'CRITICAL.*', 'exception', 'failed.*login']
        for pattern in expected_patterns:
            self.assertIn(pattern, matches)
        self.assertEqual(len(matches), 4)
    
    def test_read_new_content_empty_file(self):
        """Test reading from empty file"""
        new_lines = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(new_lines, [])
    
    def test_read_new_content_with_newlines(self):
        """Test reading content with proper newline termination"""
        test_content = "Line 1\nLine 2\nLine 3\n"
        with open(self.temp_file_path, 'w') as f:
            f.write(test_content)
        
        new_lines = self.monitor.read_new_content(self.temp_file_path)
        expected_lines = ["Line 1", "Line 2", "Line 3"]
        self.assertEqual(new_lines, expected_lines)
    
    def test_read_new_content_without_final_newline(self):
        """Test that incomplete lines (without final newline) are ignored"""
        test_content = "Line 1\nLine 2\nIncomplete line"
        with open(self.temp_file_path, 'w') as f:
            f.write(test_content)
        
        new_lines = self.monitor.read_new_content(self.temp_file_path)
        expected_lines = ["Line 1", "Line 2"]
        self.assertEqual(new_lines, expected_lines)
    
    def test_read_new_content_incremental(self):
        """Test incremental reading of file content"""
        initial_content = "Line 1\nLine 2\n"
        with open(self.temp_file_path, 'w') as f:
            f.write(initial_content)
        
        first_read = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(first_read, ["Line 1", "Line 2"])
        
        additional_content = "Line 3\nLine 4\n"
        with open(self.temp_file_path, 'a') as f:
            f.write(additional_content)
        
        second_read = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(second_read, ["Line 3", "Line 4"])
    
    def test_read_new_content_race_condition(self):
        """Test race condition handling with incomplete lines"""
        initial_content = "Line 1\nLine 2\n"
        with open(self.temp_file_path, 'w') as f:
            f.write(initial_content)
        
        first_read = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(first_read, ["Line 1", "Line 2"])
        
        # Simulate partial write (incomplete line)
        partial_content = "Line 3\nPartial"
        with open(self.temp_file_path, 'a') as f:
            f.write(partial_content)
        
        second_read = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(second_read, ["Line 3"])  # Only complete lines
        
        # Complete the partial line
        completion = " line completed\nLine 4\n"
        with open(self.temp_file_path, 'a') as f:
            f.write(completion)
        
        third_read = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(third_read, ["Partial line completed", "Line 4"])
    
    def test_utf8_handling(self):
        """Test proper UTF-8 handling in byte position tracking"""
        # Use UTF-8 characters that take multiple bytes
        initial_content = "Line 1 with émojis 🚀\nLine 2 with ñoño\n"
        with open(self.temp_file_path, 'w', encoding='utf-8') as f:
            f.write(initial_content)
        
        first_read = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(len(first_read), 2)
        self.assertIn('émojis 🚀', first_read[0])
        self.assertIn('ñoño', first_read[1])
        
        # Add more UTF-8 content
        additional_content = "Line 3 with 中文\n"
        with open(self.temp_file_path, 'a', encoding='utf-8') as f:
            f.write(additional_content)
        
        second_read = self.monitor.read_new_content(self.temp_file_path)
        self.assertEqual(second_read, ["Line 3 with 中文"])
    
    def test_alert_function(self):
        """Test alert function doesn't crash (basic functionality test)"""
        try:
            self.monitor.alert("test.log", 1, "ERROR test message", "ERROR.*")
        except Exception as e:
            self.fail(f"Alert function raised an exception: {e}")
    
    def test_custom_regex_patterns(self):
        """Test LogMonitor with custom regex patterns"""
        custom_patterns = [
            r"HTTP [45][0-9][0-9]",  # HTTP error codes
            r"timeout.*exceeded",    # Timeout errors
            r"database.*connection.*failed"  # DB connection errors
        ]
        monitor = LogMonitor([self.temp_file_path], custom_patterns)
        
        # Test HTTP error pattern
        test_line = "2025-09-05 10:01:20 INFO Request returned HTTP 404"
        matches = monitor.check_patterns(test_line)
        self.assertIn("HTTP [45][0-9][0-9]", matches)
        
        # Test timeout pattern
        test_line = "2025-09-05 10:02:30 WARN Connection timeout exceeded for user session"
        matches = monitor.check_patterns(test_line)
        self.assertIn("timeout.*exceeded", matches)
        
        # Test database pattern
        test_line = "2025-09-05 10:03:40 ERROR Database connection failed after 3 retries"
        matches = monitor.check_patterns(test_line)
        self.assertIn("database.*connection.*failed", matches)
        
        # Test no match for non-matching line
        test_line = "2025-09-05 10:00:01 INFO Normal application log"
        matches = monitor.check_patterns(test_line)
        self.assertEqual(matches, [])
    
    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex patterns"""
        invalid_patterns = [
            r"[unclosed bracket",  # Invalid regex
            r"(?P<incomplete",     # Incomplete named group
        ]
        
        # Should not raise exception, just print warnings
        monitor = LogMonitor([self.temp_file_path], invalid_patterns)
        # Should have empty patterns due to invalid regexes
        self.assertEqual(len(monitor.patterns), 0)
    
    def test_mixed_valid_invalid_patterns(self):
        """Test mix of valid and invalid regex patterns"""
        mixed_patterns = [
            r"ERROR",              # Valid
            r"[unclosed",          # Invalid  
            r"WARNING.*timeout",   # Valid
        ]
        
        monitor = LogMonitor([self.temp_file_path], mixed_patterns)
        # Should have only the valid patterns
        self.assertEqual(len(monitor.patterns), 2)
        
        # Test that valid patterns work
        test_line = "2025-09-05 10:01:20 ERROR Something failed"
        matches = monitor.check_patterns(test_line)
        self.assertIn("ERROR", matches)


class TestLogMonitorIntegration(unittest.TestCase):
    """Integration tests for the full log monitoring functionality"""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log')
        self.temp_file.close()
        self.temp_file_path = self.temp_file.name
    
    def tearDown(self):
        if os.path.exists(self.temp_file_path):
            os.unlink(self.temp_file_path)
    
    def test_end_to_end_monitoring(self):
        """Test complete monitoring workflow"""
        monitor = LogMonitor([self.temp_file_path])
        
        test_logs = [
            "2025-09-05 10:00:01 INFO Normal log entry\n",
            "2025-09-05 10:00:02 ERROR Something went wrong\n",
            "2025-09-05 10:00:03 INFO Another normal entry\n",
            "2025-09-05 10:00:04 CRITICAL System failure\n"
        ]
        
        with open(self.temp_file_path, 'w') as f:
            for log_entry in test_logs:
                f.write(log_entry)
        
        new_lines = monitor.read_new_content(self.temp_file_path)
        
        error_matches = []
        critical_matches = []
        
        for line in new_lines:
            matches = monitor.check_patterns(line)
            if 'ERROR.*' in matches:
                error_matches.append(line)
            if 'CRITICAL.*' in matches:
                critical_matches.append(line)
        
        self.assertEqual(len(error_matches), 1)
        self.assertEqual(len(critical_matches), 1)
        self.assertIn("ERROR Something went wrong", error_matches[0])
        self.assertIn("CRITICAL System failure", critical_matches[0])


if __name__ == '__main__':
    unittest.main()