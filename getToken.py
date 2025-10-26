from CloudflareBypasser import CloudflareBypasser
from DrissionPage import ChromiumPage
import time

def get_session_token_sync(max_wait=30):
    page = None
    try:
        page = ChromiumPage()
        page.get("https://spotidownloader.com/")
        
        bypasser = CloudflareBypasser(page, max_retries=3, log=True)
        bypasser.bypass()
        
        if not bypasser.is_bypassed():
            return None
        
        # Set up fetch interception
        page.run_js("""
            window.originalFetch = window.fetch;
            window.sessionToken = null;
            window.fetch = function(...args) {
                return window.originalFetch(...args).then(async response => {
                    if (response.url.includes('api.spotidownloader.com/session') || 
                        response.url.includes('/session')) {
                        try {
                            const data = await response.clone().json();
                            if (data?.token) {
                                window.sessionToken = data.token;
                                console.log('Token captured:', data.token);
                            }
                        } catch {}
                    }
                    return response;
                });
            };        
        """)
        
        # Enter a Spotify URL to trigger the session API call
        try:
            input_field = page.ele("tag:input", timeout=5)
            if input_field:
                input_field.input("https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh")
                time.sleep(1)
                
                # Find and click the download button
                buttons = page.eles("tag:button")
                for button in buttons:
                    button_text = button.text.lower() if button.text else ""
                    if any(word in button_text for word in ['herunterladen', 'download', 'fetch']):
                        button.click()
                        break
        except:
            pass
        
        # Wait for token to appear
        for _ in range(max_wait):
            try:
                token = page.run_js("return window.sessionToken")
                if token:
                    return token
            except:
                pass
            time.sleep(0.5)
        
        return None
    except:
        return None
    finally:
        if page:
            try:
                page.quit()
            except:
                pass

async def main():
    return get_session_token_sync()

def get_token():
    return get_session_token_sync()

if __name__ == "__main__":
    token = get_token()
    if token:
        print(token)