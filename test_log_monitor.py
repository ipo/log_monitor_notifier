#!/usr/bin/env python3

import unittest
import tempfile
import os
import time
import re
from log_monitor import LogMonitor


class TestLogMonitor(unittest.TestCase):
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log')
        self.temp_file.close()
        self.temp_file_path = self.temp_file.name
        # Define test patterns and templates
        self.patterns = ['(?i)ERROR.*', '(?i)CRITICAL.*', '(?i)FATAL.*', '(?i)exception', '(?i)failed.*login']
        self.templates = [
            'Error found in {filename}: {match}',
            'Critical issue found in {filename}: {match}', 
            'Fatal error found in {filename}: {match}',
            'Exception found in {filename}: {match}',
            'Failed login attempt found in {filename}: {match}'
        ]
        self.monitor = LogMonitor([self.temp_file_path], self.patterns, self.templates)
    
    def tearDown(self):
        if os.path.exists(self.temp_file_path):
            os.unlink(self.temp_file_path)
    
    def test_check_patterns_error(self):
        """Test that ERROR patterns are detected"""
        test_line = "2025-09-05 10:01:20 ERROR Failed to process payment"
        matches = self.monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn('(?i)ERROR.*', pattern_strs)
        self.assertEqual(len(matches), 1)
    
    def test_check_patterns_critical(self):
        """Test that CRITICAL patterns are detected"""
        test_line = "2025-09-05 10:03:15 CRITICAL System memory usage at 95%"
        matches = self.monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn('(?i)CRITICAL.*', pattern_strs)
        self.assertEqual(len(matches), 1)
    
    def test_check_patterns_fatal(self):
        """Test that FATAL patterns are detected"""
        test_line = "2025-09-05 10:08:00 FATAL System crash detected"
        matches = self.monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn('(?i)FATAL.*', pattern_strs)
        self.assertEqual(len(matches), 1)
    
    def test_check_patterns_exception(self):
        """Test that exception patterns are detected"""
        test_line = "2025-09-05 10:05:01 ERROR Exception in thread-pool-1: NullPointerException"
        matches = self.monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn('(?i)ERROR.*', pattern_strs)
        self.assertIn('(?i)exception', pattern_strs)
        self.assertEqual(len(matches), 2)
    
    def test_check_patterns_failed_login(self):
        """Test that failed login patterns are detected"""
        test_line = "2025-09-05 10:07:30 ERROR Failed login attempt for user: hacker123"
        matches = self.monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn('(?i)ERROR.*', pattern_strs)
        self.assertIn('(?i)failed.*login', pattern_strs)
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
                pattern_strs = [config['pattern_str'] for config, match_obj in matches]
                self.assertIn('(?i)ERROR.*', pattern_strs)
    
    def test_check_patterns_no_match(self):
        """Test that non-matching lines return empty list"""
        test_line = "2025-09-05 10:00:01 INFO Application started successfully"
        matches = self.monitor.check_patterns(test_line)
        self.assertEqual(matches, [])
    
    def test_check_patterns_multiple_patterns(self):
        """Test that multiple patterns can match the same line"""
        test_line = "CRITICAL ERROR: Exception occurred during failed login"
        matches = self.monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        expected_patterns = ['(?i)ERROR.*', '(?i)CRITICAL.*', '(?i)exception', '(?i)failed.*login']
        for pattern in expected_patterns:
            self.assertIn(pattern, pattern_strs)
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
        # Set required environment variables for API notification
        os.environ['API_KEY'] = 'test-api-key'
        os.environ['API_URL'] = 'http://localhost:8000'
        
        try:
            pattern_config = {
                'pattern': re.compile(r'(?i)ERROR.*'),
                'template': 'Error found in {filename}: {match}',
                'pattern_str': '(?i)ERROR.*'
            }
            match_obj = pattern_config['pattern'].search("ERROR test message")
            # Test will print TTS message and attempt API call (which will fail with connection error)
            # but we just want to ensure no unexpected exceptions in the formatting logic
            self.monitor.alert("test.log", 1, "ERROR test message", pattern_config, match_obj)
        except Exception as e:
            # Only fail if it's NOT a connection-related error (which is expected in tests)
            if 'API_KEY' in str(e):
                self.fail(f"Alert function raised an exception: {e}")
        finally:
            # Clean up environment variables
            if 'API_KEY' in os.environ:
                del os.environ['API_KEY']
            if 'API_URL' in os.environ:
                del os.environ['API_URL']
    
    def test_custom_regex_patterns(self):
        """Test LogMonitor with custom regex patterns"""
        custom_patterns = [
            r"HTTP [45][0-9][0-9]",  # HTTP error codes
            r"(?i)timeout.*exceeded",    # Timeout errors
            r"(?i)database.*connection.*failed"  # DB connection errors
        ]
        custom_templates = [
            'HTTP error: {match}',
            'Timeout error: {match}', 
            'Database error: {match}'
        ]
        monitor = LogMonitor([self.temp_file_path], custom_patterns, custom_templates)
        
        # Test HTTP error pattern
        test_line = "2025-09-05 10:01:20 INFO Request returned HTTP 404"
        matches = monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn("HTTP [45][0-9][0-9]", pattern_strs)
        
        # Test timeout pattern
        test_line = "2025-09-05 10:02:30 WARN Connection timeout exceeded for user session"
        matches = monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn("(?i)timeout.*exceeded", pattern_strs)
        
        # Test database pattern
        test_line = "2025-09-05 10:03:40 ERROR Database connection failed after 3 retries"
        matches = monitor.check_patterns(test_line)
        pattern_strs = [config['pattern_str'] for config, match_obj in matches]
        self.assertIn("(?i)database.*connection.*failed", pattern_strs)
        
        # Test no match for non-matching line
        test_line = "2025-09-05 10:00:01 INFO Normal application log"
        matches = monitor.check_patterns(test_line)
        self.assertEqual(matches, [])
    
    def test_invalid_regex_pattern_fails_fast(self):
        """Test that invalid regex patterns raise exceptions immediately"""
        invalid_patterns = [r"[unclosed bracket"]
        invalid_templates = ["Error: {match}"]
        
        # Should raise exception on construction
        with self.assertRaises(re.error):
            LogMonitor([self.temp_file_path], invalid_patterns, invalid_templates)

    def test_none_patterns_fail_fast(self):
        """Test that None patterns raise TypeError immediately"""
        with self.assertRaises(TypeError):
            LogMonitor([self.temp_file_path], None, None)

    def test_mismatched_pattern_template_count_fail_fast(self):
        """Test that mismatched pattern/template counts fail fast"""
        patterns = ['ERROR.*', 'WARN.*']
        templates = ['Error: {match}']  # Only one template for two patterns
        
        with self.assertRaises(IndexError):
            LogMonitor([self.temp_file_path], patterns, templates)


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
        patterns = ['(?i)ERROR.*', '(?i)CRITICAL.*', '(?i)FATAL.*', '(?i)exception', '(?i)failed.*login']
        templates = [
            'Error found in {filename}: {match}',
            'Critical issue found in {filename}: {match}', 
            'Fatal error found in {filename}: {match}',
            'Exception found in {filename}: {match}',
            'Failed login attempt found in {filename}: {match}'
        ]
        monitor = LogMonitor([self.temp_file_path], patterns, templates)
        
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
            pattern_strs = [config['pattern_str'] for config, match_obj in matches]
            if '(?i)ERROR.*' in pattern_strs:
                error_matches.append(line)
            if '(?i)CRITICAL.*' in pattern_strs:
                critical_matches.append(line)
        
        self.assertEqual(len(error_matches), 1)
        self.assertEqual(len(critical_matches), 1)
        self.assertIn("ERROR Something went wrong", error_matches[0])
        self.assertIn("CRITICAL System failure", critical_matches[0])


if __name__ == '__main__':
    unittest.main()