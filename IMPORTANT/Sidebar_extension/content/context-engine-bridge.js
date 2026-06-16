/**
 * Context Engine Bridge
 *
 * Runs in ISOLATED world to provide chrome API access for MAIN world content scripts.
 * Acts as a bridge between the page context (MAIN world) and extension APIs (ISOLATED world).
 */

(function () {
  'use strict';

  var log = function () {};
  var warn = function () {};
  var error = function () {};

  // (console suppressed)

  // Listen for messages from MAIN world content scripts
  window.addEventListener('message', function (event) {
    // Only accept messages from the same origin (our extension)
    if (event.source !== window) return;
    if (!event.data || event.data.type !== 'CONTEXT_ENGINE_BRIDGE') return;

    log('[Bridge] 📨 Received message from MAIN world:', event.data.action);

    try {
      // Check if extension context is still valid
      if (!chrome || !chrome.runtime || !chrome.runtime.sendMessage) {
        throw new Error('Extension context invalidated. Please refresh the page.');
      }

      // Additional check: try to access runtime.id (will throw if invalidated)
      try {
        const testId = chrome.runtime.id;
        if (!testId) {
          throw new Error('Extension context invalidated. Please refresh the page.');
        }
      } catch (e) {
        throw new Error('Extension context invalidated. Please refresh the page.');
      }

      if (event.data.action === 'processConversationContext') {
        // Forward the request to background script
        chrome.runtime.sendMessage({
          action: 'processConversationContext',
          extractedData: event.data.extractedData,
          triggerType: event.data.triggerType,
          autoTriggered: event.data.autoTriggered
        }, function (response) {
          // Check for runtime errors (extension might have been invalidated during the call)
          if (chrome.runtime.lastError) {
            warn('[Bridge] ⚠️ Runtime error:', chrome.runtime.lastError.message);
            window.postMessage({
              type: 'CONTEXT_ENGINE_BRIDGE_RESPONSE',
              action: event.data.action,
              requestId: event.data.requestId,
              error: 'Extension context invalidated. Please refresh the page.'
            }, '*');
            return;
          }

          // Send response back to MAIN world
          window.postMessage({
            type: 'CONTEXT_ENGINE_BRIDGE_RESPONSE',
            action: event.data.action,
            requestId: event.data.requestId,
            response: response
          }, '*');
        });
      } else if (event.data.action === 'handleMessagesExtracted') {
        // Forward to background (fire-and-forget; MAIN world has no chrome.runtime)
        chrome.runtime.sendMessage({
          action: 'handleMessagesExtracted',
          chatId: event.data.chatId,
          messages: event.data.messages,
          platform: event.data.platform,
          messageCount: event.data.messageCount,
          sessionId: event.data.sessionId
        }, function () {
          if (chrome.runtime.lastError) {
            warn('[Bridge] ⚠️ handleMessagesExtracted runtime error:', chrome.runtime.lastError.message);
          }
        });
      }
    } catch (err) {
      error('[Bridge] 💥 Error processing message:', err);

      // Send error response back to MAIN world (only if they expect a response)
      if (event.data.requestId) {
        window.postMessage({
          type: 'CONTEXT_ENGINE_BRIDGE_RESPONSE',
          action: event.data.action,
          requestId: event.data.requestId,
          error: err.message
        }, '*');
      }
    }
  });

})();