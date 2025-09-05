#!/usr/bin/env python3

import argparse
import os
import re
import time
from typing import List, Dict, Set


class LogMonitor:
    def __init__(self, files: List[str], regex_patterns: List[str] = None):
        self.files = files
        self.file_positions: Dict[str, int] = {}
        self.file_sizes: Dict[str, int] = {}
        
        # Use provided patterns or fallback to defaults
        if regex_patterns:
            self.patterns = []
            for pattern_str in regex_patterns:
                try:
                    self.patterns.append(re.compile(pattern_str, re.IGNORECASE))
                except re.error as e:
                    print(f"Warning: Invalid regex pattern '{pattern_str}': {e}")
        else:
            # Default patterns for backward compatibility
            self.patterns = [
                re.compile(r'ERROR.*', re.IGNORECASE),
                re.compile(r'CRITICAL.*', re.IGNORECASE),
                re.compile(r'FATAL.*', re.IGNORECASE),
                re.compile(r'exception', re.IGNORECASE),
                re.compile(r'failed.*login', re.IGNORECASE),
            ]
        
        for file_path in self.files:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                self.file_positions[file_path] = stat.st_size
                self.file_sizes[file_path] = stat.st_size
            else:
                self.file_positions[file_path] = 0
                self.file_sizes[file_path] = 0

    def alert(self, filename: str, line_number: int, line: str, pattern: str):
        """Alert function that prints matches"""
        print(f"ALERT: {filename}:{line_number} - Pattern '{pattern}' matched: {line.strip()}")

    def check_patterns(self, line: str) -> List[str]:
        """Check a line against all regex patterns and return matching patterns"""
        matches = []
        for pattern in self.patterns:
            if pattern.search(line):
                matches.append(pattern.pattern)
        return matches

    def read_new_content(self, file_path: str) -> List[str]:
        """Read new content from file since last position"""
        try:
            if not os.path.exists(file_path):
                return []
            
            stat = os.stat(file_path)
            current_size = stat.st_size
            last_position = self.file_positions.get(file_path, 0)
            
            if current_size <= last_position:
                return []
            
            new_lines = []
            bytes_to_read = min(current_size - last_position, 1024 * 1024)  # 1MB limit
            
            with open(file_path, 'rb') as f:
                f.seek(last_position)
                raw_content = f.read(bytes_to_read)
                
                try:
                    content = raw_content.decode('utf-8')
                except UnicodeDecodeError:
                    content = raw_content.decode('utf-8', errors='ignore')
                
                if content.endswith('\n'):
                    new_lines = content[:-1].split('\n')
                    self.file_positions[file_path] = last_position + len(raw_content)
                else:
                    lines = content.split('\n')
                    if len(lines) > 1:
                        new_lines = lines[:-1]
                        last_complete_line = '\n'.join(lines[:-1]) + '\n'
                        self.file_positions[file_path] = last_position + len(last_complete_line.encode('utf-8'))
                    
            self.file_sizes[file_path] = current_size
            return new_lines
            
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

    def monitor_files(self):
        """Main monitoring loop"""
        print(f"Starting log monitor for files: {', '.join(self.files)}")
        
        try:
            while True:
                for file_path in self.files:
                    new_lines = self.read_new_content(file_path)
                    
                    for line_num, line in enumerate(new_lines, 1):
                        if line.strip():
                            matching_patterns = self.check_patterns(line)
                            for pattern in matching_patterns:
                                self.alert(file_path, 
                                         self.file_positions.get(file_path, 0) + line_num, 
                                         line, pattern)
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")


def main():
    parser = argparse.ArgumentParser(
        description='Monitor log files for pattern matches',
        epilog=r'''
REGEX EXAMPLES:
  Basic patterns:
    --regex "ERROR"                    # Match lines containing ERROR
    --regex "WARN|ERROR"               # Match WARN or ERROR
    --regex "^[0-9]{4}-[0-9]{2}-[0-9]{2}" # Match date at start of line
    
  Complex patterns:
    --regex "failed.*login.*attempt"   # Failed login attempts
    --regex "HTTP [45][0-9][0-9]"      # HTTP 4xx/5xx errors
    --regex "exception.*stack.*trace"  # Exception stack traces
    --regex "memory.*usage.*[8-9][0-9]%" # High memory usage (80%+)
    
  Multiple patterns:
    --regex "ERROR" --regex "CRITICAL" --regex "timeout.*exceeded"
    
  Advanced examples:
    --regex "(?P<timestamp>[0-9T:-]+).*ERROR.*(?P<code>[0-9]+)"  # Named groups
    --regex "user.*(?:login|logout|failed).*(?:[0-9]{1,3}\.){3}[0-9]{1,3}"  # User activity with IP
    
NOTES:
  - Patterns are case-insensitive by default
  - Use single quotes to avoid shell escaping: --regex 'pattern with spaces'
  - Raw strings work well: --regex r'\d+\.\d+\.\d+\.\d+' 
  - If no --regex specified, uses default error/warning patterns
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('files', nargs='+', 
                       help='Log files to monitor')
    
    parser.add_argument('--regex', '-r', action='append', dest='regex_patterns',
                       help='Regex pattern to match (can be used multiple times). '
                            'If not specified, uses default error patterns.')
    
    parser.add_argument('--interval', type=float, default=1.0, 
                       help='Check interval in seconds (default: 1.0)')
    
    parser.add_argument('--case-sensitive', action='store_true',
                       help='Make regex patterns case-sensitive (default: case-insensitive)')
    
    args = parser.parse_args()
    
    # Show patterns being used
    if args.regex_patterns:
        print(f"Using {len(args.regex_patterns)} custom regex pattern(s):")
        for i, pattern in enumerate(args.regex_patterns, 1):
            print(f"  {i}. {pattern}")
    else:
        print("Using default patterns: ERROR, CRITICAL, FATAL, exception, failed.*login")
    
    monitor = LogMonitor(args.files, args.regex_patterns)
    
    # Update case sensitivity if requested
    if args.case_sensitive and args.regex_patterns:
        monitor.patterns = []
        for pattern_str in args.regex_patterns:
            try:
                monitor.patterns.append(re.compile(pattern_str))  # No re.IGNORECASE
            except re.error as e:
                print(f"Warning: Invalid regex pattern '{pattern_str}': {e}")
    
    monitor.monitor_files()


if __name__ == '__main__':
    main()