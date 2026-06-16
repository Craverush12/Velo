(function() {
  'use strict';

  // Platform-specific selectors for textareas
  const platformSelectors = {
    'openai': [
      'textarea[data-id="root"]',
      'textarea[placeholder*="Message"]',
      'div[contenteditable="true"][data-id="root"]',
      'textarea[placeholder*="Send a message"]',
      'textarea[data-testid*="textbox"]',
      'div[contenteditable="true"]',
      'textarea'
    ],
    'anthropic': [
      'textarea[placeholder*="Message Claude"]',
      'textarea[placeholder*="Talk to Claude"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="Message"]',
      'textarea'
    ],
    'google': [
      'textarea[placeholder*="Enter a prompt"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="Message"]',
      'textarea'
    ],
    'perplexity': [
      'textarea[placeholder*="Ask anything"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="Ask"]',
      'textarea'
    ],
    'mistral': [
      'textarea[placeholder*="Ask Mistral"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="Message"]',
      'textarea'
    ],
    'gamma': [
      'textarea[placeholder*="Describe what you want to create"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="prompt"]',
      'textarea'
    ],
    'bolt': [
      'textarea[placeholder*="Type your idea and we\'ll build it together"]',
      'textarea[placeholder*="Describe what you want to build"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="prompt"]',
      'textarea'
    ],
    'grok': [
      'textarea[placeholder*="Ask Grok anything"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="Message"]',
      'textarea'
    ],
    'suno': [
      'textarea[placeholder*="Describe the music"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="prompt"]',
      'textarea'
    ],
    'lovable': [
      'textarea[placeholder*="Describe your app"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="prompt"]',
      'textarea'
    ],
    'replit': [
      'textarea[placeholder*="Describe what you want to build"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="prompt"]',
      'textarea'
    ],
    'vercel': [
      'textarea[placeholder*="Describe what you want to build"]',
      'div[contenteditable="true"]',
      'textarea[placeholder*="prompt"]',
      'textarea'
    ],
    'flow': [
      'textarea',
      'div[contenteditable="true"]',
      'textarea[placeholder*="prompt"]',
      'textarea[placeholder*="message"]'
    ],
    'appalchemy': [
      'textarea[placeholder*="Describe"]',
      'textarea[placeholder*="prompt"]',
      'div[contenteditable="true"]',
      'textarea',
      'input[type="text"]'
    ],
    'kimi': [
      'textarea[placeholder*="idea" i]',
      'textarea[placeholder*="prompt" i]',
      'textarea[placeholder*="describe" i]',
      'div[contenteditable="true"]',
      'textarea',
      'input[type="text"]'
    ],
    'emergent': [
      'textarea[placeholder*="message" i]',
      'textarea[placeholder*="describe" i]',
      'textarea[placeholder*="build" i]',
      'textarea[placeholder*="idea" i]',
      'div[contenteditable="true"]',
      'textarea',
      'input[type="text"]'
    ]
  };

  // Function to detect current platform
  function detectPlatform() {
    const hostname = window.location.hostname;
    const pathname = window.location.pathname;
    
    // Updated to match the provider keys used in ExtensionUI.js
    if (hostname.includes('chat.openai.com') || hostname.includes('chatgpt.com')) return 'openai';
    if (hostname.includes('claude.ai')) return 'anthropic';
    if (hostname.includes('gemini.google.com')) return 'google';
    if (hostname.includes('perplexity.ai')) return 'perplexity';
    if (hostname.includes('chat.mistral.ai')) return 'mistral';
    if (hostname.includes('gamma.app')) return 'gamma';
    if (hostname.includes('bolt.new')) return 'bolt';
    if (hostname.includes('grok.com')) return 'grok';
    if (hostname.includes('suno.com')) return 'suno';
    if (hostname.includes('lovable.dev')) return 'lovable';
    if (hostname.includes('replit.com')) return 'replit';
    if (hostname.includes('v0.dev') || hostname.includes('v0.app')) return 'vercel';
    if (hostname.includes('labs.google') && pathname.includes('/fx/tools/flow')) return 'flow';
    if (hostname.includes('appalchemy.ai')) return 'appalchemy';
    if (hostname.includes('kimi.com')) return 'kimi';
    if (hostname.includes('app.emergent.sh') || hostname.includes('emergent.sh')) return 'emergent';
    
    return null;
  }

  // Function to find the best textarea for the current platform
  function findTextarea(platform) {
    // Helper function to check if element is visible and interactable
    function isElementVisibleAndInteractable(el) {
      if (!el || !(el instanceof Element)) return false;
      if (!document.body.contains(el)) return false;
      
      // Check basic visibility
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return false;
      if (rect.bottom < 0 || rect.right < 0 || 
          rect.top > (window.innerHeight || document.documentElement.clientHeight) || 
          rect.left > (window.innerWidth || document.documentElement.clientWidth)) {
        return false;
      }
      
      // Check computed styles
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || 
          style.visibility === 'hidden' || 
          parseFloat(style.opacity || '1') < 0.01) {
        return false;
      }
      
      // Check if element is disabled
      if (el.disabled || el.readOnly) return false;
      if (el.hasAttribute('disabled') || el.hasAttribute('readonly')) return false;
      
      // Check parent visibility
      let current = el.parentElement;
      while (current && current !== document.body) {
        const parentStyle = window.getComputedStyle(current);
        if (parentStyle.display === 'none' || parentStyle.visibility === 'hidden') {
          return false;
        }
        current = current.parentElement;
      }
      
      return true;
    }

    // Helper function to score an input element
    function scoreElement(el) {
      let score = 0;
      
      // Element type scoring
      if (el.tagName === 'TEXTAREA') score += 20;
      else if (el.tagName === 'INPUT') score += 15;
      else if (el.contentEditable === 'true' || el.isContentEditable) score += 18;
      else if (el.getAttribute('role') === 'textbox') score += 12;
      
      // Placeholder scoring
      const placeholder = (el.placeholder || el.getAttribute('placeholder') || '').toLowerCase();
      const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
      const combinedText = placeholder + ' ' + ariaLabel;
      
      if (combinedText.includes('message')) score += 25;
      if (combinedText.includes('ask')) score += 22;
      if (combinedText.includes('type')) score += 15;
      if (combinedText.includes('prompt')) score += 18;
      if (combinedText.includes('chat')) score += 20;
      
      // Focus state
      if (el === document.activeElement) score += 30;
      
      // Size scoring
      const rect = el.getBoundingClientRect();
      if (rect.width > 200 && rect.height > 30) score += 10;
      else if (rect.width > 100 && rect.height > 20) score += 5;
      
      return score;
    }

    // Step 1: Try platform-specific selectors first
    const selectors = platformSelectors[platform] || platformSelectors['openai'];
    let bestElement = null;
    let maxScore = 0;
    
    for (const selector of selectors) {
      try {
        const elements = document.querySelectorAll(selector);
        for (const element of elements) {
          if (isElementVisibleAndInteractable(element)) {
            const score = scoreElement(element);
            if (score > maxScore) {
              maxScore = score;
              bestElement = element;
            }
          }
        }
      } catch (error) {
        continue;
      }
    }
    
    if (bestElement && maxScore > 20) {
      return bestElement;
    }
    
    // Step 2: Comprehensive fallback selectors
    const fallbackSelectors = [
      'textarea[placeholder*="Message" i]',
      'textarea[placeholder*="Ask" i]',
      'textarea[data-testid*="input" i]',
      'div[contenteditable="true"][role="textbox"]',
      '[role="textbox"]',
      'textarea',
      'div[contenteditable="true"]',
      'input[type="text"]'
    ];
    
    for (const selector of fallbackSelectors) {
      try {
        const elements = document.querySelectorAll(selector);
        for (const element of elements) {
          if (isElementVisibleAndInteractable(element)) {
            const score = scoreElement(element);
            if (score > maxScore) {
              maxScore = score;
              bestElement = element;
            }
          }
        }
      } catch (error) {
        continue;
      }
    }
    
    return bestElement;
  }

  // Function to sanitize input to prevent XSS attacks
  function sanitizeInput(input) {
    if (typeof input !== 'string') return '';
    
    // Remove control characters (except newlines, tabs, carriage returns)
    let sanitized = input.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]/g, '');
    
    // Limit length to prevent DoS attacks
    const MAX_LENGTH = 50000;
    if (sanitized.length > MAX_LENGTH) {
      sanitized = sanitized.slice(0, MAX_LENGTH);
    }
    
    return sanitized;
  }

  // Function to inject text into textarea
  // SECURITY: Input is sanitized before injection to prevent XSS attacks
  function injectText(textarea, text) {
    try {
      // SECURITY: Sanitize input before injection
      const sanitizedText = sanitizeInput(text);
      if (!sanitizedText && text) return; // Only skip if original had content

      // Focus first to ensure framework listeners are active
      try { textarea.focus(); } catch (_) {}
      
      if (textarea.tagName === 'TEXTAREA' || textarea.tagName === 'INPUT') {
        // Use native value setter to bypass React/Vue controlled components
        const proto = textarea.tagName === 'TEXTAREA'
          ? window.HTMLTextAreaElement.prototype
          : window.HTMLInputElement.prototype;
        const valueSetter = Object.getOwnPropertyDescriptor(proto, 'value') &&
          Object.getOwnPropertyDescriptor(proto, 'value').set;
        if (valueSetter) {
          valueSetter.call(textarea, sanitizedText);
        } else {
          textarea.value = sanitizedText;
        }
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        textarea.dispatchEvent(new Event('keyup', { bubbles: true }));
        
      } else if (textarea.isContentEditable || textarea.contentEditable === 'true') {
        // Strategy 1: execCommand with delete first (works with most rich text editors)
        let inserted = false;
        try {
          document.execCommand('selectAll', false, null);
          document.execCommand('delete', false, null);
          inserted = document.execCommand('insertText', false, sanitizedText);
        } catch (_) {}

        // If execCommand failed or content wasn't replaced, fall back to direct assignment
        if (!inserted || (textarea.textContent || '').trim() !== sanitizedText.trim()) {
          textarea.textContent = '';
          textarea.textContent = sanitizedText;
          textarea.innerText = sanitizedText;
        }

        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        textarea.dispatchEvent(new Event('keyup', { bubbles: true }));
        
      } else {
        // Fallback for other elements
        textarea.value = sanitizedText;
        textarea.textContent = sanitizedText;
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
      }
      
      // Set cursor position to end of text
      if (textarea.setSelectionRange) {
        try { textarea.setSelectionRange(sanitizedText.length, sanitizedText.length); } catch (_) {}
      } else if (window.getSelection && document.createRange) {
        try {
          const range = document.createRange();
          range.selectNodeContents(textarea);
          range.collapse(false);
          const sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        } catch (_) {}
      }
      
      // Scroll to bottom if possible
      if (textarea.scrollTop !== undefined) {
        textarea.scrollTop = textarea.scrollHeight;
      }
      
    } catch (error) {
    }
  }

  // Function to check for stored prompt and inject it
  function checkAndInjectPrompt() {
    // First check Chrome storage (extension's native method)
    chrome.storage.local.get(['inject_prompt', 'target_provider', 'inject_timestamp'], (result) => {
      if (result.inject_prompt && result.inject_timestamp) {
        // Check if the injection is recent (within last 60 seconds)
        const now = Date.now();
        if (now - result.inject_timestamp > 60000) {
          // Clear old injection data
          chrome.storage.local.remove(['inject_prompt', 'target_provider', 'inject_timestamp']);
        } else {
          const stored = result.target_provider;
          const detected = typeof detectPlatform === 'function' ? detectPlatform() : null;
          const platform =
            (stored && platformSelectors[stored] ? stored : null) || detected;
          if (platform) {
            attemptInjection(platform, result.inject_prompt, () => {
              chrome.storage.local.remove(['inject_prompt', 'target_provider', 'inject_timestamp']);
            });
            return;
          }
        }
      }
      
      // Fallback: Check localStorage (for web app compatibility)
      try {
        const stored = localStorage.getItem('thinkvelocity_inject_prompt');
        if (stored) {
          const data = JSON.parse(stored);
          const now = Date.now();
          
          // Check if injection is recent (within last 60 seconds)
          if (now - data.timestamp > 60000) {
            localStorage.removeItem('thinkvelocity_inject_prompt');
            return;
          }
          
          const platform = typeof detectPlatform === 'function' ? detectPlatform() : null;
          if (platform) {
            attemptInjection(platform, data.prompt, () => {
              localStorage.removeItem('thinkvelocity_inject_prompt');
            });
          }
        }
      } catch (error) {
        // localStorage not available or parse error, continue silently
      }
    });
  }
  
  // Helper function to attempt injection with retries
  function attemptInjection(platform, prompt, onSuccess) {
    const attempts = [500, 1000, 2000, 3000, 5000];
    let attemptCount = 0;
    
    function tryInjection() {
      attemptCount++;
      
      const textarea = findTextarea(platform);
      if (textarea) {
        injectText(textarea, prompt);
        
        // Clear the injection data after successful injection
        if (onSuccess) {
          onSuccess();
        }
        
        return;
      } else if (attemptCount < attempts.length) {
        setTimeout(tryInjection, attempts[attemptCount]);
      }
    }
    
    // Start the first attempt
    setTimeout(tryInjection, attempts[0]);
  }

  // Run injection check when page loads
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkAndInjectPrompt);
  } else {
    checkAndInjectPrompt();
  }

  // Also check after delays in case the page loads dynamically
  setTimeout(checkAndInjectPrompt, 1000);
  setTimeout(checkAndInjectPrompt, 3000);
  setTimeout(checkAndInjectPrompt, 7000);
  setTimeout(checkAndInjectPrompt, 10000);

  // Listen for dynamic content changes
  const observer = new MutationObserver((mutations) => {
    let shouldCheck = false;
    mutations.forEach((mutation) => {
      if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
        // Check if any added nodes contain textarea or contenteditable elements
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            if (node.tagName === 'TEXTAREA' || 
                node.tagName === 'INPUT' || 
                node.isContentEditable ||
                node.querySelector('textarea, input, [contenteditable="true"]')) {
              shouldCheck = true;
            }
          }
        });
      }
    });
    
    if (shouldCheck) {
      setTimeout(checkAndInjectPrompt, 500);
    }
  });

  // Start observing
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });

  globalThis.VelocityPlatformInject = {
    injectText,
  };
})(); 