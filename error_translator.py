#!/usr/bin/env python3
"""
Error message translator for SpotiDownloader
Makes cryptic API errors human-readable
"""

def translate_error(status_code, response_text="", error_message=""):
    """
    Translate HTTP status codes and API errors into user-friendly messages
    """
    
    # HTTP Status Code translations
    status_translations = {
        400: "🚫 Bad Request - The request was invalid or malformed",
        401: "🔐 Unauthorized - Token is invalid or expired", 
        403: "⛔ Forbidden - Access denied (check your token or try refreshing)",
        404: "❌ Not Found - The requested track/album/playlist doesn't exist",
        405: "🚧 Method Not Allowed - The server doesn't support this request type",
        408: "⏱️ Request Timeout - The server took too long to respond",
        429: "🐌 Rate Limit Exceeded - Too many requests, please wait a moment",
        500: "💥 Internal Server Error - Something went wrong on the server",
        502: "🌐 Bad Gateway - Server communication error",
        503: "🔧 Service Unavailable - Server is temporarily down for maintenance",
        504: "⏰ Gateway Timeout - Server response took too long"
    }
    
    # API-specific error translations
    api_error_translations = {
        "ERR_REQUEST_INVALID": "❌ Invalid Request - Check your Spotify URL format",
        "ERR_UNAUTHORIZED": "🔐 Authentication Failed - Your token is invalid or expired",
        "ERR_FORBIDDEN": "⛔ Access Denied - This content may be region-locked or premium-only",
        "ERR_NOT_FOUND": "❌ Content Not Found - The track/album/playlist doesn't exist or was removed",
        "ERR_RATE_LIMITED": "🐌 Too Many Requests - Please wait before trying again",
        "ERR_TOKEN_EXPIRED": "⏰ Token Expired - Please fetch a new token",
        "ERR_INVALID_TOKEN": "🔑 Invalid Token - The token format is incorrect",
        "ERR_PREMIUM_REQUIRED": "💎 Premium Required - This content requires Spotify Premium",
        "ERR_REGION_BLOCKED": "🌍 Region Blocked - This content is not available in your region",
        "ERR_TRACK_UNAVAILABLE": "🚫 Track Unavailable - This track is not available for download",
        "ERR_CONNECTION_FAILED": "📡 Connection Failed - Check your internet connection"
    }
    
    # Common error pattern translations
    pattern_translations = {
        "connection": "📡 Network Problem - Check your internet connection",
        "timeout": "⏱️ Timeout - The request took too long to complete",
        "ssl": "🔒 SSL Error - Secure connection failed",
        "dns": "🌐 DNS Error - Cannot resolve server address",
        "token": "🔑 Token Issue - Try fetching a new token",
        "invalid url": "🔗 Invalid URL - Please check your Spotify URL format",
        "not found": "❌ Not Found - The content doesn't exist or was removed",
        "forbidden": "⛔ Access Denied - You don't have permission to access this",
        "rate limit": "🐌 Rate Limited - Too many requests, please wait"
    }
    
    # Start building the user-friendly message
    user_message = ""
    
    # Check status code first
    if status_code in status_translations:
        user_message = status_translations[status_code]
    
    # Check for specific API errors in response
    if response_text:
        for api_error, translation in api_error_translations.items():
            if api_error in response_text:
                user_message = translation
                break
    
    # Check for pattern matches in error message
    if not user_message and error_message:
        error_lower = error_message.lower()
        for pattern, translation in pattern_translations.items():
            if pattern in error_lower:
                user_message = translation
                break
    
    # Add helpful actions based on the error type
    action_suggestions = get_action_suggestions(status_code, response_text, error_message)
    
    # Fallback message
    if not user_message:
        user_message = f"❓ Unknown Error (Code: {status_code})"
    
    # Combine main message with suggestions
    if action_suggestions:
        full_message = f"{user_message}\n\n💡 Try this:\n{action_suggestions}"
    else:
        full_message = user_message
    
    return full_message

def get_action_suggestions(status_code, response_text="", error_message=""):
    """
    Provide actionable suggestions based on the error type
    """
    
    suggestions = []
    
    # Status code based suggestions
    if status_code in [401, 403]:
        suggestions.append("• Click 'Fetch' next to the Token field to get a new token")
        suggestions.append("• Make sure you have a stable internet connection")
    
    elif status_code == 404:
        suggestions.append("• Double-check your Spotify URL")
        suggestions.append("• Make sure the track/album/playlist is public")
        suggestions.append("• Try copying the URL from Spotify again")
    
    elif status_code == 429:
        suggestions.append("• Wait 30-60 seconds before trying again")
        suggestions.append("• Avoid making too many requests quickly")
    
    elif status_code >= 500:
        suggestions.append("• Wait a few minutes and try again")
        suggestions.append("• The server may be temporarily down")
    
    # API error based suggestions
    if "ERR_UNAUTHORIZED" in response_text or "ERR_TOKEN" in response_text:
        suggestions.append("• Fetch a new token using the 'Fetch' button")
        suggestions.append("• Make sure your browser is open when fetching tokens")
    
    elif "ERR_REQUEST_INVALID" in response_text:
        suggestions.append("• Check if your Spotify URL is complete and valid")
        suggestions.append("• Try copying the URL directly from Spotify")
    
    elif "ERR_PREMIUM" in response_text:
        suggestions.append("• This track requires Spotify Premium")
        suggestions.append("• Try a different track that's freely available")
    
    # Connection-based suggestions
    error_lower = error_message.lower() if error_message else ""
    if "connection" in error_lower or "network" in error_lower:
        suggestions.append("• Check your internet connection")
        suggestions.append("• Try disabling VPN if you're using one")
        suggestions.append("• Make sure Windows Firewall isn't blocking the app")
    
    elif "timeout" in error_lower:
        suggestions.append("• Your connection might be slow, try again")
        suggestions.append("• Check if the download server is reachable")
    
    return "\n".join(suggestions) if suggestions else ""

def format_error_for_display(status_code=None, response_text="", error_message="", context=""):
    """
    Format error for display in the SpotiDownloader UI
    """
    
    # Get the translated error
    translated_error = translate_error(status_code or 0, response_text, error_message)
    
    # Add context if provided
    if context:
        full_message = f"📍 {context}\n\n{translated_error}"
    else:
        full_message = translated_error
    
    # Add technical details for debugging (collapsible)
    if status_code or response_text or error_message:
        technical_details = []
        if status_code:
            technical_details.append(f"Status Code: {status_code}")
        if response_text and len(response_text) < 200:
            technical_details.append(f"Response: {response_text}")
        if error_message and len(error_message) < 200:
            technical_details.append(f"Error: {error_message}")
        
        if technical_details:
            full_message += f"\n\n🔧 Technical Details:\n" + " | ".join(technical_details)
    
    return full_message

# Quick test function
if __name__ == "__main__":
    # Test some common errors
    test_cases = [
        (401, '{"success":false,"message":"ERR_UNAUTHORIZED"}', ""),
        (404, "", "Track not found"),
        (429, "", "Rate limit exceeded"),
        (0, "", "Connection timeout"),
        (405, "", "Method not allowed")
    ]
    
    print("=== Error Translation Tests ===")
    for status, response, error in test_cases:
        print(f"\nInput: {status}, {response}, {error}")
        print(f"Output: {translate_error(status, response, error)}")
        print("-" * 50)