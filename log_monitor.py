#!/usr/bin/env python3

import argparse
import glob
import os
import re
import sys
import time
import requests
from typing import List, Dict, Optional


def _format_regex_compile_error(pattern_index: int, pattern_str: str, err: re.error) -> str:
    """Return a user-friendly error message showing where regex compilation failed."""
    message_lines = [
        f"Invalid regular expression for --regex #{pattern_index + 1}: {pattern_str!r}"
    ]

    lines = pattern_str.splitlines() or [pattern_str]
    lineno = getattr(err, 'lineno', None)
    colno = getattr(err, 'colno', None)

    if lineno is None or lineno < 1 or lineno > len(lines):
        lineno = 1

    if colno is None:
        pos = getattr(err, 'pos', None)
        colno = (pos + 1) if isinstance(pos, int) and pos >= 0 else None

    if 1 <= lineno <= len(lines):
        prefix = f"  Line {lineno}: "
        line_text = lines[lineno - 1]
        message_lines.append(prefix + line_text)

        if isinstance(colno, int) and colno > 0:
            caret_indent = " " * len(prefix) + " " * (colno - 1)
            message_lines.append(caret_indent + "^")

    message_lines.append(f"re.error: {err}")
    return "\n".join(message_lines)


class LogMonitor:
    def __init__(
        self,
        files: List[str],
        regex_patterns: List[str] = None,
        tts_templates: List[str] = None,
        maximum_lifetime_hours: int = 1,
        pattern_specs: Optional[List[Dict[str, object]]] = None,
        poll_interval: float = 1.0,
        pattern_refresh_interval: float = 30.0,
    ):
        self.files: List[str] = []
        self.file_positions: Dict[str, int] = {}
        self.file_sizes: Dict[str, int] = {}
        self.maximum_lifetime_hours = maximum_lifetime_hours
        self.pattern_specs = pattern_specs or []
        self.poll_interval = max(poll_interval, 0.01)
        self.pattern_refresh_interval = pattern_refresh_interval if pattern_refresh_interval > 0 else self.poll_interval
        self.next_pattern_refresh = time.monotonic()

        # Use provided patterns - no defaults
        self.pattern_configs = []
        for i, pattern_str in enumerate(regex_patterns or []):
            try:
                compiled_pattern = re.compile(pattern_str)
            except re.error as err:
                message = _format_regex_compile_error(i, pattern_str, err)
                raise ValueError(message) from err

            template = tts_templates[i]
            self.pattern_configs.append({
                'pattern': compiled_pattern,
                'template': template,
                'pattern_str': pattern_str
            })

        for file_path in files:
            self._register_file(file_path)

        # Initial pattern refresh to pick up any existing matches immediately
        self.refresh_patterns(force=True)

    def _register_file(self, file_path: str):
        """Add a file to tracking, starting at its current size."""
        abs_path = os.path.abspath(file_path)

        if abs_path in self.file_positions:
            return

        if abs_path not in self.files:
            self.files.append(abs_path)

        if os.path.exists(abs_path):
            stat = os.stat(abs_path)
            self.file_positions[abs_path] = stat.st_size
            self.file_sizes[abs_path] = stat.st_size
            print(f"Added file to monitor: {abs_path}")
        else:
            self.file_positions[abs_path] = 0
            self.file_sizes[abs_path] = 0

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
            file_path = os.path.abspath(file_path)
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
        if self.files:
            print(f"Starting log monitor for files: {', '.join(self.files)}")
        else:
            print("Starting log monitor with no initial files.")

        if self.pattern_specs:
            print("Monitoring glob patterns:")
            for spec in self.pattern_specs:
                print(f"  - {spec['pattern']}")

        try:
            while True:
                self.refresh_patterns()

                for file_path in list(self.file_positions.keys()):
                    new_lines = self.read_new_content(file_path)
                    
                    for line_num, line in enumerate(new_lines, 1):
                        if line.strip():
                            matching_patterns = self.check_patterns(line)
                            for pattern_config, match_obj in matching_patterns:
                                self.alert(file_path, 
                                         self.file_positions.get(file_path, 0) + line_num, 
                                         line, pattern_config, match_obj)
                
                time.sleep(self.poll_interval)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")

    def refresh_patterns(self, force: bool = False):
        """Refresh glob patterns to discover new files."""
        if not self.pattern_specs:
            return

        now = time.monotonic()
        if not force and now < self.next_pattern_refresh:
            return

        for spec in self.pattern_specs:
            pattern = spec['pattern']
            recursive = spec.get('recursive', False)
            for matched_path in glob.iglob(pattern, recursive=recursive):
                if os.path.isdir(matched_path):
                    continue
                self._register_file(matched_path)

        self.next_pattern_refresh = now + self.pattern_refresh_interval


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

    parser.add_argument('--pattern-refresh-interval', type=float, default=30.0,
                       help='How often to rescan glob patterns for new files in seconds (default: 30.0)')

    args = parser.parse_args()
    
    # Validate template count matches pattern count
    if len(args.regex_patterns) != len(args.tts_templates):
        parser.error(f"Number of --template arguments ({len(args.tts_templates)}) must match number of --regex arguments ({len(args.regex_patterns)})")

    pattern_specs = []
    initial_files: List[str] = []

    for raw_path in args.files:
        if glob.has_magic(raw_path):
            recursive = '**' in raw_path
            pattern_specs.append({'pattern': raw_path, 'recursive': recursive})
            for matched in glob.glob(raw_path, recursive=recursive):
                if os.path.isdir(matched):
                    continue
                initial_files.append(matched)
        else:
            initial_files.append(raw_path)

    # Show patterns being used
    print(f"Using {len(args.regex_patterns)} custom regex pattern(s):")
    for i, pattern in enumerate(args.regex_patterns, 1):
        template = args.tts_templates[i-1]
        print(f"  {i}. Pattern: {pattern}")
        print(f"     Template: {template}")

    try:
        monitor = LogMonitor(
            initial_files,
            args.regex_patterns,
            args.tts_templates,
            args.maximum_lifetime_hours,
            pattern_specs=pattern_specs,
            poll_interval=args.interval,
            pattern_refresh_interval=args.pattern_refresh_interval,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    monitor.monitor_files()


if __name__ == '__main__':
    main()
