/**
 * Smart Trigger Manager - triggers essence updates with throttling and rate limiting.
 */
(function () {
  'use strict';

  // Debug flag - set to true to enable console logging
  // Console logging enabled - all console output is active
  var log = console.log.bind(console);
  var warn = console.warn.bind(console);
  var error = console.error.bind(console);
  var info = console.info.bind(console);

  /**
   * Smart Trigger Manager Class
   * 
   * Default configuration optimized for balanced API usage:
   * - minWordCountDelta: 10 words (meaningful content change)
   * - minTimeBetweenUpdates: 1000ms (1 second throttle)
   * - maxUpdatesPerHour: 60 (reasonable rate limit)
   * - streamingDebounceTime: 1000ms (wait for streaming)
   * - minMessages: 5 (minimum conversation depth)
   */
  function SmartTriggerManager(config) {
    // Configuration with defaults
    this.config = {
      minWordCountDelta: config?.minWordCountDelta || 10,          // Minimum 10 new words for meaningful change
      minTimeBetweenUpdates: config?.minTimeBetweenUpdates || 1000, // 1 second between updates
      maxUpdatesPerHour: config?.maxUpdatesPerHour || 60,          // 60 updates per hour max
      streamingDebounceTime: config?.streamingDebounceTime || 1000, // Wait for streaming to complete
      minMessages: config?.minMessages || 5                        // At least 5 messages required
    };

    // Session state (persisted in browser storage)
    this.sessionState = {
      lastUpdateTime: 0,
      lastWordCount: 0,
      currentConversationId: null,  // Track current conversation to detect switches
      updatesThisHour: 0,
      hourStartTime: Date.now(),
      analytics: {
        totalTriggers: 0,
        blockedTriggers: 0,
        blockReasons: {}
      }
    };

    // Debounced processing function
    this.debouncedProcess = null;
    this.debounceTimer = null;

    // Initialize from storage
    this.loadSessionState();

    // Reset hourly counter if hour has passed
    this.resetHourlyCounterIfNeeded();
  }

  /**
   * Load session state from browser storage
   */
  SmartTriggerManager.prototype.loadSessionState = function () {
    var self = this;

    // Check if chrome.storage is available
    if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
      // Fallback to localStorage if chrome.storage not available
      try {
        var stored = localStorage.getItem('smartTriggerState');
        if (stored) {
          var parsed = JSON.parse(stored);
          // Only restore if data is recent (within last hour)
          if (parsed.hourStartTime && (Date.now() - parsed.hourStartTime < 3600000)) {
            self.sessionState.lastUpdateTime = parsed.lastUpdateTime || 0;
            self.sessionState.lastWordCount = parsed.lastWordCount || 0;
            self.sessionState.currentConversationId = parsed.currentConversationId || null;
            self.sessionState.updatesThisHour = parsed.updatesThisHour || 0;
            self.sessionState.hourStartTime = parsed.hourStartTime || Date.now();
          }
          // Always restore analytics (cumulative)
          if (parsed.analytics) {
            self.sessionState.analytics = parsed.analytics;
          }
        }
      } catch (e) {
        // localStorage not available or parse error
        warn('[SmartTriggerManager] Could not load session state from localStorage:', e);
      }
      return;
    }

    // Use chrome.storage if available
    try {
      chrome.storage.local.get(['smartTriggerState'], function (result) {
        if (chrome.runtime.lastError) {
          warn('[SmartTriggerManager] Could not load session state:', chrome.runtime.lastError);
          return;
        }

        if (result.smartTriggerState) {
          var stored = result.smartTriggerState;
          // Only restore if data is recent (within last hour)
          if (stored.hourStartTime && (Date.now() - stored.hourStartTime < 3600000)) {
            self.sessionState.lastUpdateTime = stored.lastUpdateTime || 0;
            self.sessionState.lastWordCount = stored.lastWordCount || 0;
            self.sessionState.currentConversationId = stored.currentConversationId || null;
            self.sessionState.updatesThisHour = stored.updatesThisHour || 0;
            self.sessionState.hourStartTime = stored.hourStartTime || Date.now();
          }
          // Always restore analytics (cumulative)
          if (stored.analytics) {
            self.sessionState.analytics = stored.analytics;
          }
        }
      });
    } catch (e) {
      // Storage not available (e.g., in test environment)
      warn('[SmartTriggerManager] Could not load session state:', e);
    }
  };

  /**
   * Save session state to browser storage
   */
  SmartTriggerManager.prototype.saveSessionState = function () {
    var stateToSave = {
      lastUpdateTime: this.sessionState.lastUpdateTime,
      lastWordCount: this.sessionState.lastWordCount,
      currentConversationId: this.sessionState.currentConversationId,
      updatesThisHour: this.sessionState.updatesThisHour,
      hourStartTime: this.sessionState.hourStartTime,
      analytics: this.sessionState.analytics
    };

    // Check if chrome.storage is available
    if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
      // Fallback to localStorage if chrome.storage not available
      try {
        localStorage.setItem('smartTriggerState', JSON.stringify(stateToSave));
      } catch (e) {
        // localStorage not available or quota exceeded
        warn('[SmartTriggerManager] Could not save session state to localStorage:', e);
      }
      return;
    }

    // Use chrome.storage if available
    try {
      chrome.storage.local.set({
        smartTriggerState: stateToSave
      }, function () {
        if (chrome.runtime.lastError) {
          warn('[SmartTriggerManager] Could not save session state:', chrome.runtime.lastError);
        }
      });
    } catch (e) {
      // Storage not available
      warn('[SmartTriggerManager] Could not save session state:', e);
    }
  };

  /**
   * Reset hourly counter if an hour has passed
   */
  SmartTriggerManager.prototype.resetHourlyCounterIfNeeded = function () {
    var now = Date.now();
    var hourElapsed = now - this.sessionState.hourStartTime;

    if (hourElapsed >= 3600000) { // 1 hour = 3600000ms
      this.sessionState.updatesThisHour = 0;
      this.sessionState.hourStartTime = now;
      this.saveSessionState();
    }
  };

  /**
   * Count words in text
   */
  SmartTriggerManager.prototype.countWords = function (text) {
    if (!text || typeof text !== 'string') return 0;
    // Remove extra whitespace and split by spaces
    var cleaned = text.trim().replace(/\s+/g, ' ');
    if (cleaned.length === 0) return 0;
    return cleaned.split(' ').length;
  };

  /**
   * Calculate total word count from messages
   */
  SmartTriggerManager.prototype.calculateTotalWordCount = function (messages) {
    if (!Array.isArray(messages)) return 0;

    var totalWords = 0;
    for (var i = 0; i < messages.length; i++) {
      var message = messages[i];
      if (message && message.content) {
        totalWords += this.countWords(message.content);
      }
    }
    return totalWords;
  };

  /**
   * Check if streaming is currently active
   */
  SmartTriggerManager.prototype.isStreamingActive = function () {
    // Check for common streaming indicators
    var streamingIndicators = [
      '.animate-pulse',
      '[data-streaming="true"]',
      '.typing-indicator',
      '[class*="streaming"]',
      '[class*="typing"]'
    ];

    for (var i = 0; i < streamingIndicators.length; i++) {
      try {
        if (document.querySelector(streamingIndicators[i])) {
          return true;
        }
      } catch (e) {
        // Selector might be invalid, continue
      }
    }

    return false;
  };

  /**
   * Determine if essence update should be triggered
   * Returns: { shouldTrigger: boolean, reason: string, details: object }
   */
  SmartTriggerManager.prototype.shouldTriggerEssenceUpdate = function (changeEvent) {
    log('[SmartTrigger] 🔍 Evaluating trigger conditions...', {
      trigger: changeEvent.trigger,
      messageCount: (changeEvent.messages || changeEvent.data?.conversation?.messages || []).length,
      hasConversationData: !!changeEvent.data?.conversation
    });

    this.resetHourlyCounterIfNeeded();

    var messages = changeEvent.messages || changeEvent.data?.conversation?.messages || [];
    var totalWords = this.calculateTotalWordCount(messages);

    // ═══════════════════════════════════════════════════════════════════════════
    // DETECT CONVERSATION SWITCH - Reset state when switching conversations
    // ═══════════════════════════════════════════════════════════════════════════
    var conversationData = changeEvent.data?.conversation || changeEvent.data || changeEvent;
    var currentConversationId = conversationData.sessionId || conversationData.session_id || 
                                conversationData.chatId || conversationData.id || null;
    
    // Also check if trigger indicates new conversation
    var isNewConversation = changeEvent.trigger === 'new_conversation';
    
    // If conversation ID changed OR it's explicitly a new conversation, reset state
    var conversationChanged = currentConversationId && 
                            this.sessionState.currentConversationId !== currentConversationId;
    
    if (isNewConversation || conversationChanged) {
      log('[SmartTrigger] 🔄 Conversation switch detected:', {
        trigger: changeEvent.trigger,
        isNewConversation: isNewConversation,
        conversationChanged: conversationChanged,
        oldConversationId: this.sessionState.currentConversationId,
        newConversationId: currentConversationId,
        oldWordCount: this.sessionState.lastWordCount
      });
      
      // Reset word count for new conversation (treat as fresh start)
      this.sessionState.lastWordCount = 0;
      if (currentConversationId) {
        this.sessionState.currentConversationId = currentConversationId;
      }
      this.saveSessionState();
      
      log('[SmartTrigger] ✅ Reset state for new conversation (wordCount reset to 0)');
    }

    // Block 1: Currently streaming - wait for completion
    if (this.isStreamingActive()) {
      return {
        shouldTrigger: false,
        reason: 'streaming_in_progress',
        details: {
          message: 'Streaming detected - waiting for completion',
          totalWords: totalWords
        }
      };
    }

    // Block 2: Too recent update
    var timeSinceLastUpdate = Date.now() - this.sessionState.lastUpdateTime;
    if (timeSinceLastUpdate < this.config.minTimeBetweenUpdates) {
      var remainingSeconds = Math.ceil((this.config.minTimeBetweenUpdates - timeSinceLastUpdate) / 1000);
      return {
        shouldTrigger: false,
        reason: 'too_recent',
        details: {
          message: 'Update too recent - wait ' + remainingSeconds + ' more seconds',
          timeSinceLastUpdate: timeSinceLastUpdate,
          minTimeBetweenUpdates: this.config.minTimeBetweenUpdates,
          remainingSeconds: remainingSeconds
        }
      };
    }

    // Block 3: Insufficient new content (word count delta)
    // Skip this check if lastWordCount is 0 (new conversation - already reset above)
    var wordCountDelta = totalWords - this.sessionState.lastWordCount;
    if (wordCountDelta < this.config.minWordCountDelta && this.sessionState.lastWordCount > 0) {
      return {
        shouldTrigger: false,
        reason: 'insufficient_content',
        details: {
          message: 'Insufficient new content - need ' + (this.config.minWordCountDelta - wordCountDelta) + ' more words',
          wordCountDelta: wordCountDelta,
          minWordCountDelta: this.config.minWordCountDelta,
          currentTotal: totalWords,
          lastTotal: this.sessionState.lastWordCount,
          note: 'This check is skipped for new conversations (lastWordCount = 0)'
        }
      };
    }
    
    // If wordCountDelta is negative and lastWordCount > 0, it means we're comparing against wrong conversation
    // This shouldn't happen if conversation switch detection worked, but add safety check
    if (wordCountDelta < 0 && this.sessionState.lastWordCount > 0 && !isNewConversation) {
      warn('[SmartTrigger] ⚠️ Negative word delta detected - possible conversation switch not detected:', {
        wordCountDelta: wordCountDelta,
        currentTotal: totalWords,
        lastTotal: this.sessionState.lastWordCount,
        currentConversationId: currentConversationId,
        lastConversationId: this.sessionState.currentConversationId
      });
      // Reset to allow this conversation (safety fallback)
      this.sessionState.lastWordCount = 0;
      if (currentConversationId) {
        this.sessionState.currentConversationId = currentConversationId;
      }
      this.saveSessionState();
      log('[SmartTrigger] ✅ Safety reset applied - treating as new conversation');
    }

    // Block 4: Rate limiting (max updates per hour)
    if (this.sessionState.updatesThisHour >= this.config.maxUpdatesPerHour) {
      var nextResetSeconds = Math.ceil((3600000 - (Date.now() - this.sessionState.hourStartTime)) / 1000);
      return {
        shouldTrigger: false,
        reason: 'rate_limited',
        details: {
          message: 'Rate limit exceeded - ' + this.config.maxUpdatesPerHour + ' updates/hour. Resets in ' + nextResetSeconds + ' seconds',
          updatesThisHour: this.sessionState.updatesThisHour,
          maxUpdatesPerHour: this.config.maxUpdatesPerHour,
          nextResetSeconds: nextResetSeconds
        }
      };
    }

    // Block 5: Empty or invalid content
    if (!messages || messages.length < this.config.minMessages) {
      return {
        shouldTrigger: false,
        reason: 'insufficient_messages',
        details: {
          message: 'Insufficient messages - need at least ' + this.config.minMessages,
          messageCount: messages ? messages.length : 0,
          minMessages: this.config.minMessages
        }
      };
    }

    // Block 6: No actual content (all messages empty)
    var hasContent = false;
    for (var i = 0; i < messages.length; i++) {
      if (messages[i] && messages[i].content && messages[i].content.trim().length > 0) {
        hasContent = true;
        break;
      }
    }
    if (!hasContent) {
      return {
        shouldTrigger: false,
        reason: 'no_content',
        details: {
          message: 'No content found in messages',
          messageCount: messages.length
        }
      };
    }

    // Passed all checks - proceed with update
    log('[SmartTrigger] ✅ All checks passed - WILL TRIGGER API CALL', {
      totalWords: totalWords,
      wordCountDelta: wordCountDelta,
      messageCount: messages.length
    });

    return {
      shouldTrigger: true,
      reason: 'valid_update',
      details: {
        message: 'All checks passed - triggering update',
        totalWords: totalWords,
        wordCountDelta: wordCountDelta,
        updatesThisHour: this.sessionState.updatesThisHour + 1,
        timeSinceLastUpdate: timeSinceLastUpdate
      }
    };
  };

  /**
   * Update analytics
   */
  SmartTriggerManager.prototype.updateAnalytics = function (eventType, reason) {
    this.sessionState.analytics.totalTriggers++;

    if (eventType === 'trigger_blocked') {
      this.sessionState.analytics.blockedTriggers++;
      if (!this.sessionState.analytics.blockReasons[reason]) {
        this.sessionState.analytics.blockReasons[reason] = 0;
      }
      this.sessionState.analytics.blockReasons[reason]++;
    }

    this.saveSessionState();
  };

  /**
   * Get analytics data
   */
  SmartTriggerManager.prototype.getAnalytics = function () {
    return {
      totalTriggers: this.sessionState.analytics.totalTriggers,
      blockedTriggers: this.sessionState.analytics.blockedTriggers,
      allowedTriggers: this.sessionState.analytics.totalTriggers - this.sessionState.analytics.blockedTriggers,
      blockRate: this.sessionState.analytics.totalTriggers > 0
        ? (this.sessionState.analytics.blockedTriggers / this.sessionState.analytics.totalTriggers * 100).toFixed(2) + '%'
        : '0%',
      blockReasons: this.sessionState.analytics.blockReasons,
      currentHour: {
        updatesThisHour: this.sessionState.updatesThisHour,
        maxUpdatesPerHour: this.config.maxUpdatesPerHour,
        remainingUpdates: Math.max(0, this.config.maxUpdatesPerHour - this.sessionState.updatesThisHour)
      }
    };
  };

  /**
   * Reset analytics (for testing or manual reset)
   */
  SmartTriggerManager.prototype.resetAnalytics = function () {
    this.sessionState.analytics = {
      totalTriggers: 0,
      blockedTriggers: 0,
      blockReasons: {}
    };
    this.saveSessionState();
  };

  /**
   * Process DOM change event with intelligent triggering
   * @param {Object} changeEvent - Change event from extractor
   * @param {Function} callback - Callback to execute if trigger is allowed
   * @param {Function} originalExtractionFn - Original extraction function to call
   */
  SmartTriggerManager.prototype.onDOMChange = function (changeEvent, callback, originalExtractionFn) {
    var self = this;

    // Debug logging
    if (window.SMART_TRIGGER_DEBUG) {
      log('[SmartTriggerManager] onDOMChange called', {
        trigger: changeEvent.trigger,
        messageCount: changeEvent.messages ? changeEvent.messages.length : 0,
        hasData: !!changeEvent.data
      });
    }

    // Clear any existing debounce timer
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    // Debounce processing to handle rapid changes
    this.debounceTimer = setTimeout(function () {
      self.processIfNeeded(changeEvent, callback, originalExtractionFn);
    }, this.config.streamingDebounceTime);
  };

  /**
   * Process change event if it meets criteria
   */
  SmartTriggerManager.prototype.processIfNeeded = function (changeEvent, callback, originalExtractionFn) {
    var triggerResult = this.shouldTriggerEssenceUpdate(changeEvent);

    if (!triggerResult.shouldTrigger) {
      log('⏭️ [SmartTrigger] BLOCKED: ' + triggerResult.reason, triggerResult.details);
      this.updateAnalytics('trigger_blocked', triggerResult.reason);
      return;
    }

    log('🚀 [SmartTrigger] Triggering essence update: ' + triggerResult.reason, triggerResult.details);

    // Debug logging
    if (window.SMART_TRIGGER_DEBUG) {
      log('[SmartTriggerManager] processIfNeeded - allowing trigger', triggerResult);
    }

    // Update state
    var messages = changeEvent.messages || changeEvent.data?.conversation?.messages || [];
    var totalWords = this.calculateTotalWordCount(messages);

    this.sessionState.lastUpdateTime = Date.now();
    this.sessionState.lastWordCount = totalWords;
    this.sessionState.updatesThisHour++;
    this.saveSessionState();

    this.updateAnalytics('essence_triggered', triggerResult.reason);

    // Send conversation data to ContextEngine for processing
    this.sendToContextEngine(changeEvent);

    // Call the original extraction function
    if (typeof originalExtractionFn === 'function') {
      originalExtractionFn(changeEvent, callback);
    } else if (typeof callback === 'function') {
      // Fallback: call callback directly
      callback(changeEvent);
    }
  };

  /**
   * Send conversation data to ContextEngine for AI processing
   * Uses the context-engine-bridge.js for MAIN world to ISOLATED world communication
   */
  SmartTriggerManager.prototype.sendToContextEngine = function (changeEvent) {
    try {
      // Extract conversation data from change event
      var conversationData = changeEvent.data || changeEvent;

      // Ensure we have the required data structure
      if (!conversationData || !conversationData.conversation) {
        warn('[SmartTrigger] No conversation data available for ContextEngine');
        return;
      }

      // Generate unique request ID for tracking
      var requestId = 'smart_trigger_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

      log('[SmartTrigger] 📤 Sending to ContextEngine via bridge:', {
        requestId: requestId,
        messageCount: conversationData.conversation?.messages?.length || 0,
        platform: conversationData.conversation?.platform || 'unknown'
      });

      // Set up response handler. We track the timeout so an arriving response
      // can cancel it (otherwise the 30s "Bridge response timeout" still
      // fires after a real HTTP 4xx/5xx and pollutes the console).
      var timeoutId = null;

      function cleanupBridgeHandlers() {
        window.removeEventListener('message', handleBridgeResponse);
        if (timeoutId !== null) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
      }

      function handleBridgeResponse(event) {
        if (event.data.type === 'CONTEXT_ENGINE_BRIDGE_RESPONSE' &&
            event.data.requestId === requestId) {

          cleanupBridgeHandlers();

          if (event.data.error) {
            error('[SmartTrigger] ❌ Bridge error:', event.data.error);
          } else if (event.data.response && event.data.response.success) {
              log('✅ [SmartTrigger] ContextEngine processing completed');
              log('[SmartTrigger] 📄 API Response:', event.data.response.contextResult);
          } else {
              var errMsg = event.data.response && event.data.response.error;
              if (typeof errMsg === 'string' && /HTTP 5\d\d/.test(errMsg)) {
                // Server-side failures (5xx) are ContextEngine errors, not
                // ours. Log once at warn level without the full body so the
                // host console stays readable.
                warn('⚠️ [SmartTrigger] ContextEngine server error (will retry on next eligible trigger)');
              } else {
                warn('⚠️ [SmartTrigger] ContextEngine processing failed:', errMsg);
              }
          }
        }
      }

      window.addEventListener('message', handleBridgeResponse);

      // Send via bridge (MAIN world -> ISOLATED world -> background script)
      window.postMessage({
        type: 'CONTEXT_ENGINE_BRIDGE',
        action: 'processConversationContext',
        requestId: requestId,
        extractedData: conversationData.conversation,
        triggerType: changeEvent.trigger || 'smart_trigger',
        autoTriggered: true
      }, '*');

      // Timeout after 30 seconds. Cleared automatically when a response
      // arrives via cleanupBridgeHandlers().
      timeoutId = setTimeout(function () {
        timeoutId = null;
        window.removeEventListener('message', handleBridgeResponse);
        warn('[SmartTrigger] ⏰ Bridge response timeout');
      }, 30000);

    } catch (error) {
      error('[SmartTrigger] Error sending to ContextEngine:', error);
    }
  };

  /**
   * Force trigger (bypasses all checks) - for manual triggers
   */
  SmartTriggerManager.prototype.forceTrigger = function (changeEvent, callback, originalExtractionFn) {
    log('🔓 [SmartTrigger] Force triggering essence update (bypassing checks)');

    // Update state but don't increment counter (manual trigger)
    var messages = changeEvent.messages || changeEvent.data?.conversation?.messages || [];
    var totalWords = this.calculateTotalWordCount(messages);

    this.sessionState.lastUpdateTime = Date.now();
    this.sessionState.lastWordCount = totalWords;
    this.saveSessionState();

    // Send conversation data to ContextEngine for processing
    this.sendToContextEngine(changeEvent);

    // Call the original extraction function
    if (typeof originalExtractionFn === 'function') {
      originalExtractionFn(changeEvent, callback);
    } else if (typeof callback === 'function') {
      callback(changeEvent);
    }
  };

  /**
   * Get current status
   */
  SmartTriggerManager.prototype.getStatus = function () {
    this.resetHourlyCounterIfNeeded();

    return {
      config: this.config,
      sessionState: {
        lastUpdateTime: this.sessionState.lastUpdateTime,
        lastWordCount: this.sessionState.lastWordCount,
        updatesThisHour: this.sessionState.updatesThisHour,
        maxUpdatesPerHour: this.config.maxUpdatesPerHour,
        remainingUpdates: Math.max(0, this.config.maxUpdatesPerHour - this.sessionState.updatesThisHour),
        timeSinceLastUpdate: Date.now() - this.sessionState.lastUpdateTime,
        nextAllowedUpdate: this.sessionState.lastUpdateTime + this.config.minTimeBetweenUpdates
      },
      analytics: this.getAnalytics(),
      isStreaming: this.isStreamingActive()
    };
  };

  /**
   * Direct API trigger function - bypasses extension messaging
   * Usage: triggerContextEngineDirect() - extracts and sends directly to API
   */
  if (typeof window !== 'undefined') {
    /**
     * Send custom data directly to ContextEngine API
     * Usage: sendToContextEngine(customData) - sends any JSON to the API
     */
    window.sendToContextEngine = async function (customData) {
      log('[Direct API] 🚀 Sending custom data to ContextEngine API');

      try {
        if (!customData) {
          error('[Direct API] ❌ No data provided');
          return { success: false, error: 'No data provided' };
        }

        log('[Direct API] 📤 Sending request to https://thinkvelocity.in/context-engine/api/process-context');
        log('[Direct API] 📋 Request payload:', JSON.stringify(customData, null, 2));

        // Use bridge to communicate with ISOLATED world
        var requestId = 'send_custom_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        function handleBridgeResponse(event) {
          if (event.data.type === 'CONTEXT_ENGINE_BRIDGE_RESPONSE' &&
            event.data.requestId === requestId) {

            window.removeEventListener('message', handleBridgeResponse);

            if (event.data.error) {
              error('[Direct API] ❌ Bridge error:', event.data.error);
              resolve({ success: false, error: event.data.error });
            } else if (event.data.response && event.data.response.success) {
              log('[Direct API] ✅ API call successful!');
              log('[Direct API] 📄 Response data:', JSON.stringify(event.data.response.contextResult, null, 2));
              resolve({ success: true, data: event.data.response.contextResult });
            } else {
              error('[Direct API] ❌ API call failed:', event.data.response?.error);
              resolve({ success: false, error: event.data.response?.error || 'Unknown error' });
            }
          }
        }

        window.addEventListener('message', handleBridgeResponse);

        // Normalize platform to lowercase (backend requires: chatgpt, claude, gemini, mistral, velocity)
        const normalizePlatform = (platform) => {
          if (!platform) return "chatgpt";
          const normalized = platform.toLowerCase().trim();
          // Map alternative names to valid values
          const platformMap = {
            'openai': 'chatgpt',
            'anthropic': 'claude',
            'google': 'gemini'
          };
          return platformMap[normalized] || normalized;
        };

        // Check if customData is already in ExtensionSyncRequest format
        let processedData = customData;
        if (customData.user_id || customData.session_id || customData.messages) {
          // Convert simple format to ExtensionSyncRequest format
          processedData = {
            sessionId: customData.session_id || customData.sessionId || "custom_session",
            sessionStartedAt: Date.now(),
            exportedAt: Date.now(),
            platform: normalizePlatform(customData.platform),
            extractorVersion: "3.1.4",
            user: {
              user_id: customData.user_id || "custom_user",
              usage_left: 100,
              accessToken: null,
              accessTokenExpiresAt: null
            },
            stats: {},
            conversations: [{
              chatId: customData.session_id || customData.sessionId || "custom_session",
              title: "Custom Conversation",
              url: window.location.href,
              messages: (customData.messages || []).map((msg, index) => ({
                role: msg.role,
                content: msg.content,
                timestamp: typeof msg.timestamp === 'string' ? msg.timestamp : new Date().toISOString(),
                index: index,
                contentType: "plain",
                images: [],
                codeBlocks: []
              })),
              model: "gpt-4",
              updatedAt: Date.now()
            }]
          };
        }

        window.postMessage({
          type: 'CONTEXT_ENGINE_BRIDGE',
          action: 'processConversationContext',
          requestId: requestId,
          extractedData: processedData,
          triggerType: 'custom_data',
          autoTriggered: false
        }, '*');

        // Timeout after 10 seconds
        setTimeout(function () {
          window.removeEventListener('message', handleBridgeResponse);
          warn('[Direct API] ⏰ Bridge response timeout for custom data');
          resolve({ success: false, error: 'Bridge response timeout' });
        }, 10000);

        log('[Direct API] 📡 Response status:', response.status, response.statusText);

        if (!response.ok) {
          const errorText = await response.text();
          error('[Direct API] ❌ API call failed:', response.status);
          error('[Direct API] 📄 Error response:', errorText);
          return { success: false, error: `HTTP ${response.status}: ${errorText}` };
        }

        const result = await response.json();
        log('[Direct API] ✅ API call successful!');
        log('[Direct API] 📄 Response data:', JSON.stringify(result, null, 2));

        return { success: true, data: result };

      } catch (error) {
        error('[Direct API] 💥 Error:', error);
        return { success: false, error: error.message };
      }
    };

    window.triggerContextEngineDirect = async function () {
      log('[Direct API] 🚀 Direct ContextEngine API trigger initiated');

      try {
        // Find the appropriate extractor
        var currentUrl = window.location.href;
        var extractor = null;

        if (currentUrl.includes('chatgpt.com') || currentUrl.includes('chat.openai.com')) {
          extractor = window.VelocityChatGPTExtractor;
          log('[Direct API] 📍 Detected ChatGPT platform');
        } else if (currentUrl.includes('claude.ai')) {
          extractor = window.VelocityClaudeExtractor;
          log('[Direct API] 📍 Detected Claude platform');
        } else if (currentUrl.includes('gemini.google.com')) {
          extractor = window.VelocityGeminiExtractor;
          log('[Direct API] 📍 Detected Gemini platform');
        } else {
          error('[Direct API] ❌ Unsupported platform for direct API call');
          return { success: false, error: 'Unsupported platform' };
        }

        if (!extractor) {
          error('[Direct API] ❌ Extractor not found for current platform');
          return { success: false, error: 'Extractor not loaded' };
        }

        // Extract conversation data
        log('[Direct API] 📊 Extracting conversation data...');
        var conversationData = extractor.extractConversation ? extractor.extractConversation() : extractor.extract();

        if (!conversationData || !conversationData.success || !conversationData.messages || conversationData.messages.length === 0) {
          error('[Direct API] ❌ No conversation data to process');
          return { success: false, error: 'No conversation data available' };
        }

        log('[Direct API] 📊 Extracted data:', {
          sessionId: conversationData.sessionId,
          messageCount: conversationData.messages.length,
          platform: conversationData.platform
        });

        // Normalize platform to lowercase (backend requires: chatgpt, claude, gemini, mistral, velocity)
        const normalizePlatform = (platform) => {
          if (!platform) return "chatgpt";
          const normalized = platform.toLowerCase().trim();
          // Map alternative names to valid values
          const platformMap = {
            'openai': 'chatgpt',
            'anthropic': 'claude',
            'google': 'gemini'
          };
          return platformMap[normalized] || normalized;
        };

        // Transform to ExtensionSyncRequest format (required by ContextEngine)
        const contextPayload = {
          sessionId: conversationData.sessionId || conversationData.session_id || "unknown_session",
          sessionStartedAt: Date.now(),
          exportedAt: Date.now(),
          platform: normalizePlatform(conversationData.platform),
          extractorVersion: "3.1.4",
          user: {
            user_id: conversationData.user?.user_id || conversationData.userId || "unknown_user",
            usage_left: conversationData.user?.usage_left || 100,
            accessToken: conversationData.user?.accessToken || null,
            accessTokenExpiresAt: conversationData.user?.accessTokenExpiresAt || null
          },
          stats: conversationData.stats || {},
          conversations: [{
            chatId: conversationData.sessionId || conversationData.session_id || "unknown_session",
            title: conversationData.title || "Chat Conversation",
            url: conversationData.url || window.location.href,
            messages: (conversationData.messages || []).map((msg, index) => ({
              role: msg.role,
              content: msg.content,
              timestamp: typeof msg.timestamp === 'string' ? msg.timestamp :
                (msg.timestamp ? new Date(msg.timestamp).toISOString() : new Date().toISOString()),
              index: index,
              contentType: msg.contentType || "plain",
              images: msg.images || [],
              codeBlocks: msg.codeBlocks || []
            })),
            model: conversationData.model || "gpt-4",
            updatedAt: Date.now()
          }]
        };

        log('[Direct API] 📤 Sending request to https://thinkvelocity.in/context-engine/api/process-context');
        log('[Direct API] 📋 Request payload:', JSON.stringify(contextPayload, null, 2));

        // Make direct API call
        // Use bridge to communicate with ISOLATED world
        var requestId = 'direct_api_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        function handleBridgeResponse(event) {
          if (event.data.type === 'CONTEXT_ENGINE_BRIDGE_RESPONSE' &&
            event.data.requestId === requestId) {

            window.removeEventListener('message', handleBridgeResponse);

            if (event.data.error) {
              error('[Direct API] ❌ Bridge error:', event.data.error);
              resolve({ success: false, error: event.data.error });
            } else if (event.data.response && event.data.response.success) {
              log('[Direct API] ✅ API call successful!');
              log('[Direct API] 📄 Response data:', JSON.stringify(event.data.response.contextResult, null, 2));
              resolve({ success: true, data: event.data.response.contextResult });
            } else {
              error('[Direct API] ❌ API call failed:', event.data.response?.error);
              resolve({ success: false, error: event.data.response?.error || 'Unknown error' });
            }
          }
        }

        window.addEventListener('message', handleBridgeResponse);

        window.postMessage({
          type: 'CONTEXT_ENGINE_BRIDGE',
          action: 'processConversationContext',
          requestId: requestId,
          extractedData: { ...contextPayload, success: true, sessionId: contextPayload.session_id, platform: contextPayload.platform },
          triggerType: 'direct_api_call',
          autoTriggered: false
        }, '*');

        // Timeout after 10 seconds
        setTimeout(function () {
          window.removeEventListener('message', handleBridgeResponse);
          warn('[Direct API] ⏰ Bridge response timeout for direct API call');
          resolve({ success: false, error: 'Bridge response timeout' });
        }, 10000);

        log('[Direct API] 📡 Response status:', response.status, response.statusText);

        if (!response.ok) {
          const errorText = await response.text();
          error('[Direct API] ❌ API call failed:', response.status);
          error('[Direct API] 📄 Error response:', errorText);
          return { success: false, error: `HTTP ${response.status}: ${errorText}` };
        }

        const result = await response.json();
        log('[Direct API] ✅ API call successful!');
        log('[Direct API] 📄 Response data:', JSON.stringify(result, null, 2));

        return { success: true, data: result };

      } catch (error) {
        error('[Direct API] 💥 Error:', error);
        return { success: false, error: error.message };
      }
    };

    /**
     * Test ContextEngine API connectivity
     * Usage: testContextEngineAPI() - checks if API is reachable
     */
    window.testContextEngineAPI = async function () {
      log('[Test] 🧪 Testing ContextEngine API connectivity...');

      try {
        // Test payload in ExtensionSyncRequest format
        const testData = {
          sessionId: "test_session",
          sessionStartedAt: Date.now(),
          exportedAt: Date.now(),
          platform: "test",
          extractorVersion: "3.1.4",
          user: {
            user_id: "test_user",
            usage_left: 100,
            accessToken: null,
            accessTokenExpiresAt: null
          },
          stats: {},
          conversations: [{
            chatId: "test_session",
            title: "Test Conversation",
            url: window.location.href,
            messages: [
              { role: "user", content: "Hello", timestamp: new Date().toISOString(), index: 0, contentType: "plain", images: [], codeBlocks: [] },
              { role: "assistant", content: "Hi there!", timestamp: new Date().toISOString(), index: 1, contentType: "plain", images: [], codeBlocks: [] }
            ],
            model: "gpt-4",
            updatedAt: Date.now()
          }]
        };

        log('[Test] 📤 Sending test request...');
        // Use bridge to communicate with ISOLATED world
        var requestId = 'test_api_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        function handleBridgeResponse(event) {
          if (event.data.type === 'CONTEXT_ENGINE_BRIDGE_RESPONSE' &&
            event.data.requestId === requestId) {

            window.removeEventListener('message', handleBridgeResponse);

            const response = event.data.response;
            if (event.data.error) {
              error('[Test] ❌ Bridge error:', event.data.error);
              resolve({ success: false, reachable: false, error: event.data.error });
            } else if (response && response.success) {
              log('[Test] ✅ API is reachable and responding!');
              log('[Test] 📄 Test response:', response.contextResult);
              resolve({ success: true, reachable: true, response: response.contextResult });
            } else {
              log('[Test] ⚠️ API responded but with error:', response?.error);
              log('[Test] 📄 Error details:', response?.error);
              resolve({ success: true, reachable: true, error: response?.error });
            }
          }
        }

        window.addEventListener('message', handleBridgeResponse);

        window.postMessage({
          type: 'CONTEXT_ENGINE_BRIDGE',
          action: 'processConversationContext',
          requestId: requestId,
          extractedData: testData,
          triggerType: 'api_test',
          autoTriggered: false
        }, '*');

        // Timeout after 10 seconds
        setTimeout(function () {
          window.removeEventListener('message', handleBridgeResponse);
          error('[Test] ❌ API is not reachable - ContextEngine may not be running');
          error('[Test] 💡 Make sure ContextEngine is running on https://thinkvelocity.in/context-engine');
          resolve({ success: false, reachable: false, error: 'API not reachable' });
        }, 10000);

        log('[Test] 📡 Response status:', response.status);

        if (response.ok) {
          const result = await response.json();
          log('[Test] ✅ API is reachable and responding!');
          log('[Test] 📄 Test response:', result);
          return { success: true, reachable: true, response: result };
        } else {
          const errorText = await response.text();
          log('[Test] ⚠️ API responded but with error:', response.status);
          log('[Test] 📄 Error details:', errorText);
          return { success: true, reachable: true, error: `HTTP ${response.status}: ${errorText}` };
        }

      } catch (error) {
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
          error('[Test] ❌ API is not reachable - ContextEngine may not be running');
          error('[Test] 💡 Make sure ContextEngine is running on https://thinkvelocity.in/context-engine');
          return { success: false, reachable: false, error: 'API not reachable' };
        } else {
          error('[Test] ❌ Unexpected error:', error);
          return { success: false, reachable: false, error: error.message };
        }
      }
    };

    window.triggerContextEngineAPI = function () {
      log('[Global] 🚀 Triggering ContextEngine API from current page');

      // Find the appropriate extractor based on current URL
      var currentUrl = window.location.href;
      var extractor = null;

      if (currentUrl.includes('chatgpt.com') || currentUrl.includes('chat.openai.com')) {
        extractor = window.VelocityChatGPTExtractor;
        log('[Global] 📍 Detected ChatGPT platform');
      } else if (currentUrl.includes('claude.ai')) {
        extractor = window.VelocityClaudeExtractor;
        log('[Global] 📍 Detected Claude platform');
      } else if (currentUrl.includes('gemini.google.com')) {
        extractor = window.VelocityGeminiExtractor;
        log('[Global] 📍 Detected Gemini platform');
      } else {
        error('[Global] ❌ Unsupported platform for ContextEngine API');
        return { success: false, error: 'Unsupported platform' };
      }

      if (!extractor) {
        error('[Global] ❌ Extractor not found for current platform');
        return { success: false, error: 'Extractor not loaded' };
      }

      if (!extractor.triggerContextEngine) {
        error('[Global] ❌ triggerContextEngine function not available');
        return { success: false, error: 'Trigger function not available' };
      }

      // Call the platform-specific trigger function
      return extractor.triggerContextEngine();
    };

    window.SmartTriggerManager = SmartTriggerManager;
  }

  // Also support CommonJS/Node-like environments
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = SmartTriggerManager;
  }

})();

