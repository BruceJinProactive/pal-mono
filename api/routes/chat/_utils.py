class URLFilter:
    """
    Filter that detects and removes URLs from stream chunks.

    The filter uses a buffer to track potential URL fragments across multiple chunks,
    since URLs might be split between different chunks in the stream. For example,
    if one chunk ends with "https" and the next begins with "://example.com", the filter
    will detect and remove the complete URL.

    It doesn't support multiple urls in the same segment

    """

    def __init__(self):
        self.string_buffer: str = ""
        self.partial_prefixes = (
            "https:/",
            "https:",
            "https",
            "http:/",
            "http:",
            "http",
            "htt",
            "ht",
            "h",
        )

    def _find_url_start_index(self) -> int:
        """Check if the buffer contains the start of a URL (http:// or https://)."""
        for prefix in ("https://", "http://"):
            index = self.string_buffer.find(prefix)
            if index != -1:
                return index
        return -1

    def _find_url_end_index(self, start: int) -> int:
        """
        Check if the buffer contains characters indicating a potential URL end:
        - Space
        - Line break
        - Parenthesis
        """
        for i in range(start, len(self.string_buffer)):
            if self.string_buffer[i] in (" ", "\n", "\r", ")"):
                return i
        return -1

    def _find_partial_prefix_end(self) -> int:
        for prefix in self.partial_prefixes:
            if self.string_buffer.endswith(prefix):
                return len(self.string_buffer) - len(prefix)
        return -1

    def filter_content(self, chunk: str) -> str:
        """
        Filter URL content from a chunk.

        Args:
            content: A content string from a chunk

        Returns:
            Filtered content with URLs removed
        """
        self.string_buffer += chunk
        start = self._find_url_start_index()
        # Whole url is in the buffer
        if start != -1:
            end = self._find_url_end_index(start)
            if end != -1:
                # Remove the URL from buffer
                result = self.string_buffer[:start] + self.string_buffer[end:]
                self.string_buffer = ""  # Reset buffer
                return result
            else:
                result = self.string_buffer[:start]
                self.string_buffer = self.string_buffer[start:]
                return result

        # If we didn't find a complete URL, check for partial prefix at the end
        partial_end = self._find_partial_prefix_end()
        if partial_end != -1:
            result = self.string_buffer[:partial_end]
            self.string_buffer = self.string_buffer[partial_end:]
            return result
        # No URL or partial prefix found, return entire buffer
        result = self.string_buffer
        self.string_buffer = ""
        return result


def create_url_filter() -> URLFilter:
    return URLFilter()
