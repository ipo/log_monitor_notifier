#!/usr/bin/env python3

import argparse
import os
import re
import time
import requests
from typing import List, Dict, Set, Optional


class LogMonitor:
    def __init__(self, files: List[str], regex_patterns: List[str] = None, tts_templates: List[str] = None, maximum_lifetime_hours: int = 1):
        self.files = files
        self.file_positions: Dict[str, int] = {}
        self.file_sizes: Dict[str, int] = {}
        self.maximum_lifetime_hours = maximum_lifetime_hours
        
        # Use provided patterns - no defaults
        self.pattern_configs = []
        for i, pattern_str in enumerate(regex_patterns):
            compiled_pattern = re.compile(pattern_str)
            template = tts_templates[i]
            self.pattern_configs.append({
                'pattern': compiled_pattern,
                'template': template,
                'pattern_str': pattern_str
            })
        
        for file_path in self.files:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                self.file_positions[file_path] = stat.st_size
                self.file_sizes[file_path] = stat.st_size
            else:
                self.file_positions[file_path] = 0
                self.file_sizes[file_path] = 0

    def send_api_notification(self, tts_message: str, maximum_lifetime_hours: int = 1) -> bool:
        """Send notification to remote API using environment variables for config"""
        api_key = os.environ['API_KEY']
        url = os.environ['API_URL']
        
        # Prepare request data - only title and tts_text are used
        data = {
            "title": tts_message,
            "tts_text": tts_message,
            "maximum_lifetime_hours": maximum_lifetime_hours
        }
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key
        }
        
        # Make API request
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                print(f"API notification failed with status {response.status_code}")
                return False
                
        except Exception as e:
            print(f"API notification error: {e}")
            return False

    def alert(self, filename: str, line_number: int, line: str, pattern_config: dict, match_obj):
        """Alert function that formats matches using TTS templates"""
        import os
        
        # Prepare template variables
        template_vars = {
            'filename': os.path.basename(filename),
            'line_number': line_number,
            'match': line.strip()
        }
        
        # Add named groups from regex match
        if match_obj and match_obj.groupdict():
            template_vars.update(match_obj.groupdict())
        
        # Format the TTS message
        tts_message = pattern_config['template'].format(**template_vars)
        print(f"TTS: {tts_message}")
        
        # Send API notification
        self.send_api_notification(tts_message, self.maximum_lifetime_hours)

    def check_patterns(self, line: str) -> List[tuple]:
        """Check a line against all regex patterns and return matching pattern configs with match objects"""
        matches = []
        for pattern_config in self.pattern_configs:
            match_obj = pattern_config['pattern'].search(line)
            if match_obj:
                matches.append((pattern_config, match_obj))
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
                
                content = raw_content.decode('utf-8')
                
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
                            for pattern_config, match_obj in matching_patterns:
                                self.alert(file_path, 
                                         self.file_positions.get(file_path, 0) + line_num, 
                                         line, pattern_config, match_obj)
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")


def main():
    parser = argparse.ArgumentParser(
        description='Monitor log files for pattern matches',
        epilog=r'''
REGEX AND TTS TEMPLATE EXAMPLES:
  Basic patterns with TTS templates:
    --regex "(?i)ERROR" --template "Error detected in {filename}"
    --regex "(?i)WARN|ERROR" --template "Warning or error found in {filename}: {match}"
    
  Named groups in templates:
    --regex "(?P<timestamp>[0-9T:-]+).*(?i:ERROR).*(?P<code>[0-9]+)" \
    --template "Error code {code} at {timestamp} in {filename}"
    
  Multiple patterns with templates:
    --regex "(?i)failed.*login.*attempt" --template "Failed login in {filename}" \
    --regex "HTTP [45][0-9][0-9]" --template "HTTP error in {filename}: {match}" \
    --regex "(?i)exception.*stack.*trace" --template "Exception with stack trace in {filename}"
    
  Template variables available:
    {filename}     # Log filename without path (e.g., "app.log")
    {line_number}  # Line number where match occurred
    {match}        # Full matched text
    {groupname}    # Any named regex groups (e.g., (?P<groupname>...))
    
INLINE REGEX MODIFIERS:
  (?i)           # Case-insensitive matching
  (?x)           # Verbose mode (ignore whitespace and comments)
  (?a)           # ASCII-only matching
  (?u)           # Unicode matching (default in Python 3)
  (?L)           # Locale-dependent matching
  (?i:pattern)   # Case-insensitive for specific group only
  (?-i:pattern)  # Case-sensitive for specific group only
  
  Combinations:
  (?ix)          # Case-insensitive + verbose mode
  (?i)ERROR|(?-i)WARN  # Mixed case sensitivity
  
NOTES:
  - Number of --template arguments must match number of --regex arguments
  - Patterns are case-sensitive by default (use (?i) for case-insensitive)
  - Use single quotes to avoid shell escaping issues
  - All --regex and --template arguments are required
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('files', nargs='+', 
                       help='Log files to monitor')
    
    parser.add_argument('--regex', '-r', action='append', dest='regex_patterns', required=True,
                       help='Regex pattern to match (can be used multiple times). Required.')
    
    parser.add_argument('--template', '-t', action='append', dest='tts_templates', required=True,
                       help='TTS template for corresponding regex pattern. Must match number of --regex arguments. '
                            'Template variables: {filename}, {line_number}, {match}, and any named groups from regex.')
    
    parser.add_argument('--interval', type=float, default=1.0, 
                       help='Check interval in seconds (default: 1.0)')
    
    parser.add_argument('--maximum_lifetime_hours', type=int, default=1,
                       help='Maximum lifetime in hours for notifications (default: 1, range: 1-8760)')
    
    args = parser.parse_args()
    
    # Validate template count matches pattern count
    if len(args.regex_patterns) != len(args.tts_templates):
        parser.error(f"Number of --template arguments ({len(args.tts_templates)}) must match number of --regex arguments ({len(args.regex_patterns)})")
    
    # Show patterns being used
    print(f"Using {len(args.regex_patterns)} custom regex pattern(s):")
    for i, pattern in enumerate(args.regex_patterns, 1):
        template = args.tts_templates[i-1]
        print(f"  {i}. Pattern: {pattern}")
        print(f"     Template: {template}")
    
    monitor = LogMonitor(args.files, args.regex_patterns, args.tts_templates, args.maximum_lifetime_hours)
    
    monitor.monitor_files()


if __name__ == '__main__':
    main()