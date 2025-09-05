#!/usr/bin/env python3

import argparse
import os
import re
import time
from typing import List, Dict, Set


class LogMonitor:
    def __init__(self, files: List[str], regex_patterns: List[str] = None, tts_templates: List[str] = None):
        self.files = files
        self.file_positions: Dict[str, int] = {}
        self.file_sizes: Dict[str, int] = {}
        
        # Use provided patterns or fallback to defaults
        if regex_patterns:
            self.pattern_configs = []
            for i, pattern_str in enumerate(regex_patterns):
                try:
                    compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
                    template = tts_templates[i] if tts_templates and i < len(tts_templates) else "Match found in {filename}: {match}"
                    self.pattern_configs.append({
                        'pattern': compiled_pattern,
                        'template': template,
                        'pattern_str': pattern_str
                    })
                except re.error as e:
                    print(f"Warning: Invalid regex pattern '{pattern_str}': {e}")
        else:
            # Default patterns for backward compatibility
            self.pattern_configs = [
                {'pattern': re.compile(r'ERROR.*', re.IGNORECASE), 'template': 'Error found in {filename}: {match}', 'pattern_str': 'ERROR.*'},
                {'pattern': re.compile(r'CRITICAL.*', re.IGNORECASE), 'template': 'Critical issue found in {filename}: {match}', 'pattern_str': 'CRITICAL.*'},
                {'pattern': re.compile(r'FATAL.*', re.IGNORECASE), 'template': 'Fatal error found in {filename}: {match}', 'pattern_str': 'FATAL.*'},
                {'pattern': re.compile(r'exception', re.IGNORECASE), 'template': 'Exception found in {filename}: {match}', 'pattern_str': 'exception'},
                {'pattern': re.compile(r'failed.*login', re.IGNORECASE), 'template': 'Failed login attempt found in {filename}: {match}', 'pattern_str': 'failed.*login'},
            ]
        
        for file_path in self.files:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                self.file_positions[file_path] = stat.st_size
                self.file_sizes[file_path] = stat.st_size
            else:
                self.file_positions[file_path] = 0
                self.file_sizes[file_path] = 0

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
        try:
            tts_message = pattern_config['template'].format(**template_vars)
            print(f"TTS: {tts_message}")
        except KeyError as e:
            print(f"TTS Template Error: Missing variable {e} in template '{pattern_config['template']}'")
            print(f"FALLBACK ALERT: {filename}:{line_number} - Pattern '{pattern_config['pattern_str']}' matched: {line.strip()}")

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
    --regex "ERROR" --template "Error detected in {filename}"
    --regex "WARN|ERROR" --template "Warning or error found in {filename}: {match}"
    
  Named groups in templates:
    --regex "(?P<timestamp>[0-9T:-]+).*ERROR.*(?P<code>[0-9]+)" \
    --template "Error code {code} at {timestamp} in {filename}"
    
  Multiple patterns with templates:
    --regex "failed.*login.*attempt" --template "Failed login in {filename}" \
    --regex "HTTP [45][0-9][0-9]" --template "HTTP error in {filename}: {match}" \
    --regex "exception.*stack.*trace" --template "Exception with stack trace in {filename}"
    
  Template variables available:
    {filename}     # Log filename without path (e.g., "app.log")
    {line_number}  # Line number where match occurred
    {match}        # Full matched text
    {groupname}    # Any named regex groups (e.g., (?P<groupname>...))
    
NOTES:
  - Number of --template arguments must match number of --regex arguments
  - Patterns are case-insensitive by default (use --case-sensitive to change)
  - Use single quotes to avoid shell escaping issues
  - If no --regex specified, uses default error/warning patterns with default templates
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('files', nargs='+', 
                       help='Log files to monitor')
    
    parser.add_argument('--regex', '-r', action='append', dest='regex_patterns',
                       help='Regex pattern to match (can be used multiple times). '
                            'If not specified, uses default error patterns.')
    
    parser.add_argument('--template', '-t', action='append', dest='tts_templates',
                       help='TTS template for corresponding regex pattern. Must match number of --regex arguments. '
                            'Template variables: {filename}, {line_number}, {match}, and any named groups from regex.')
    
    parser.add_argument('--interval', type=float, default=1.0, 
                       help='Check interval in seconds (default: 1.0)')
    
    parser.add_argument('--case-sensitive', action='store_true',
                       help='Make regex patterns case-sensitive (default: case-insensitive)')
    
    args = parser.parse_args()
    
    # Validate template count matches pattern count
    if args.regex_patterns and args.tts_templates:
        if len(args.regex_patterns) != len(args.tts_templates):
            parser.error(f"Number of --template arguments ({len(args.tts_templates)}) must match number of --regex arguments ({len(args.regex_patterns)})")
    
    # Show patterns being used
    if args.regex_patterns:
        print(f"Using {len(args.regex_patterns)} custom regex pattern(s):")
        for i, pattern in enumerate(args.regex_patterns, 1):
            template = args.tts_templates[i-1] if args.tts_templates else "Match found in {filename}: {match}"
            print(f"  {i}. Pattern: {pattern}")
            print(f"     Template: {template}")
    else:
        print("Using default patterns: ERROR, CRITICAL, FATAL, exception, failed.*login")
    
    monitor = LogMonitor(args.files, args.regex_patterns, args.tts_templates)
    
    # Update case sensitivity if requested
    if args.case_sensitive and args.regex_patterns:
        for i, pattern_config in enumerate(monitor.pattern_configs):
            try:
                pattern_config['pattern'] = re.compile(pattern_config['pattern_str'])  # No re.IGNORECASE
            except re.error as e:
                print(f"Warning: Invalid regex pattern '{pattern_config['pattern_str']}': {e}")
    
    monitor.monitor_files()


if __name__ == '__main__':
    main()