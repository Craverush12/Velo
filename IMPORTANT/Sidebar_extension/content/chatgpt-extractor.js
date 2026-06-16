/**
 * ChatGPT Conversation Extractor - DOM-resilient extraction for ChatGPT (MAIN world).
 */
(function () {
  'use strict';

  // Prevent double initialization
  if (window.VelocityChatGPTExtractor) {
    return;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CONSOLE HELPERS
  // Quiet by default in Sidebar_extension. Errors always print; log/warn/info
  // print only when localStorage.velocity_sidebar_debug === '1' (set in the
  // host page DevTools, not the extension console).
  // ═══════════════════════════════════════════════════════════════════════════
  function __velocityHostQuiet() {
    try {
      if (typeof window !== 'undefined' && window.__VELOCITY_EXTRACTOR_DEBUG__) return false;
      if (typeof localStorage !== 'undefined' && localStorage.getItem('velocity_sidebar_debug') === '1') return false;
    } catch (e) { /* ignore */ }
    return true;
  }
  var log = function () { if (__velocityHostQuiet()) return; console.log.apply(console, arguments); };
  var warn = function () { if (__velocityHostQuiet()) return; console.warn.apply(console, arguments); };
  var info = function () { if (__velocityHostQuiet()) return; console.info.apply(console, arguments); };
  var error = console.error.bind(console);

  // ═══════════════════════════════════════════════════════════════════════════
  // CONFIGURATION & CONSTANTS
  // ═══════════════════════════════════════════════════════════════════════════

  var CONFIG = {
    PLATFORM: 'chatgpt',
    TIMESTAMP_INTERVAL_MS: 25000,
    MIN_TEXT_LENGTH: 5,
    MIN_VISIBLE_HEIGHT: 20,
    DEBUG: false,  // Set to false to reduce console noise
    VERBOSE: false,  // Set to true only for detailed debugging
    VERSION: '2.0.0',
    // Cache & tracking settings
    CACHE_ENABLED: true,
    DEBOUNCE_MS: 500,
    STREAMING_CHECK_INTERVAL: 200,
    MAX_CACHE_AGE_MS: 30 * 60 * 1000, // 30 minutes
    AUTO_TRACK: true,
    // Storage settings
    COMPRESS_STORAGE: true,
    MAX_STORED_CHATS: 50,
    MAX_MESSAGES_PER_CHAT: 100
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // COMPRESSION UTILITIES (LZ-based compression for localStorage)
  // ═══════════════════════════════════════════════════════════════════════════

  var Compression = {
    /**
     * Compress string using LZ-based algorithm
     * Reduces JSON size by 60-80%
     */
    compress: function (str) {
      if (!str) return '';
      try {
        // Simple LZ compression using built-in encoding
        var compressed = this._lzCompress(str);
        return compressed;
      } catch (e) {
        error('Compression failed:', e);
        return str; // Return original if compression fails
      }
    },

    /**
     * Decompress string
     */
    decompress: function (compressed) {
      if (!compressed) return '';
      try {
        return this._lzDecompress(compressed);
      } catch (e) {
        error('Decompression failed:', e);
        return compressed; // Return as-is if decompression fails
      }
    },

    /**
     * LZ-based compression (simplified)
     */
    _lzCompress: function (input) {
      var dict = {};
      var data = (input + '').split('');
      var out = [];
      var currChar;
      var phrase = data[0];
      var code = 256;

      for (var i = 1; i < data.length; i++) {
        currChar = data[i];
        if (dict[phrase + currChar] != null) {
          phrase += currChar;
        } else {
          out.push(phrase.length > 1 ? dict[phrase] : phrase.charCodeAt(0));
          dict[phrase + currChar] = code;
          code++;
          phrase = currChar;
        }
      }
      out.push(phrase.length > 1 ? dict[phrase] : phrase.charCodeAt(0));

      // Convert to base64-like string
      return btoa(JSON.stringify(out));
    },

    /**
     * LZ-based decompression
     */
    _lzDecompress: function (compressed) {
      if (!compressed || typeof compressed !== 'string') {
        throw new Error('Invalid compressed data: not a string');
      }

      try {
        // Try to decode base64
        var decoded = atob(compressed);
        if (!decoded) {
          throw new Error('Failed to decode base64');
        }

        // Try to parse JSON
        var data = JSON.parse(decoded);
        if (!Array.isArray(data) || data.length === 0) {
          throw new Error('Invalid decompressed data: not an array');
        }

        var dict = {};
        var currChar = String.fromCharCode(data[0]);
        var oldPhrase = currChar;
        var out = [currChar];
        var code = 256;
        var phrase;

        for (var i = 1; i < data.length; i++) {
          var currCode = data[i];
          if (typeof currCode !== 'number') {
            throw new Error('Invalid data format at index ' + i);
          }
          if (currCode < 256) {
            phrase = String.fromCharCode(currCode);
          } else {
            phrase = dict[currCode] ? dict[currCode] : (oldPhrase + currChar);
          }
          out.push(phrase);
          currChar = phrase.charAt(0);
          dict[code] = oldPhrase + currChar;
          code++;
          oldPhrase = phrase;
        }
        return out.join('');
      } catch (e) {
        // Re-throw with more context
        throw new Error('Decompression failed: ' + e.message);
      }
    },

    /**
     * Generate hash for validation
     */
    generateHash: function (str) {
      var hash = 0;
      for (var i = 0; i < str.length; i++) {
        var char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
      }
      return 'v_' + Math.abs(hash).toString(36);
    },

    /**
     * Validate content against hash
     */
    validate: function (content, expectedHash) {
      var actualHash = this.generateHash(JSON.stringify(content));
      return actualHash === expectedHash;
    }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // DATA CACHE & STATE MANAGEMENT
  // ═══════════════════════════════════════════════════════════════════════════

  var DataCache = {
    // Current state
    currentChatId: null,
    currentUrl: null,

    // Conversation cache: { chatId: { hash, data, timestamp, messageCount } }
    conversations: {},

    // Sidebar cache: { hash, data, timestamp, chatCount }
    sidebar: null,

    // Event listeners
    listeners: [],

    // State flags
    isStreaming: false,
    lastExtractionTime: 0,
    pendingExtraction: null,

    /**
     * Generate hash from content for comparison
     */
    generateHash: function (data) {
      var str = JSON.stringify(data);
      var hash = 0;
      for (var i = 0; i < str.length; i++) {
        var char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
      }
      return 'h_' + Math.abs(hash).toString(36);
    },

    /**
     * Extract chat ID from URL
     */
    getChatIdFromUrl: function (url) {
      url = url || window.location.href;
      var match = url.match(/\/c\/([a-f0-9-]+)/i);
      return match ? match[1] : null;
    },

    /**
     * Check if we're on a conversation page
     */
    isConversationPage: function () {
      return this.getChatIdFromUrl() !== null;
    },

    /**
     * Check if assistant is currently streaming a response
     */
    checkIsStreaming: function () {
      // Look for streaming indicators
      var streamingSelectors = [
        '[class*="streaming"]',
        '[class*="result-streaming"]',
        '[data-testid*="stop"]',
        'button[aria-label*="Stop"]',
        '.agent-turn [class*="cursor"]'
      ];

      for (var i = 0; i < streamingSelectors.length; i++) {
        if (document.querySelector(streamingSelectors[i])) {
          return true;
        }
      }

      // Check for stop button visibility
      var stopBtn = document.querySelector('button[data-testid="stop-button"]');
      if (stopBtn && stopBtn.offsetParent !== null) {
        return true;
      }

      return false;
    },

    /**
     * Wait for streaming to complete.
     *
     * Re-entry guard: ChatGPT's React reconciler emits a flurry of DOM
     * mutations while streaming, and each mutation can re-enter
     * `handleDomChange`. Without the guard, every burst spawns a fresh
     * 200ms-poll loop that runs for up to maxWait — producing the
     * thousand-frame `check @ ...` stack chain visible in DevTools.
     *
     * When a wait is already in flight, we queue the new callback against
     * the same poll loop instead of starting another.
     */
    _waitForStreamingCompleteActive: false,
    _streamingCallbacks: [],
    waitForStreamingComplete: function (callback, maxWait) {
      var self = this;
      maxWait = maxWait || 60000; // 60 second max

      if (typeof callback === 'function') {
        self._streamingCallbacks.push(callback);
      }

      if (self._waitForStreamingCompleteActive) {
        return;
      }

      self._waitForStreamingCompleteActive = true;
      var startTime = Date.now();

      function flushCallbacks() {
        var callbacks = self._streamingCallbacks;
        self._streamingCallbacks = [];
        self._waitForStreamingCompleteActive = false;
        callbacks.forEach(function (cb) {
          try { cb(); } catch (e) { /* ignore */ }
        });
      }

      function check() {
        if (!self.checkIsStreaming()) {
          setTimeout(flushCallbacks, 100); // Small delay for DOM to settle
          return;
        }
        if (Date.now() - startTime > maxWait) {
          flushCallbacks();
          return;
        }
        setTimeout(check, CONFIG.STREAMING_CHECK_INTERVAL);
      }

      check();
    },

    /**
     * Get cached conversation data
     */
    getConversationCache: function (chatId) {
      chatId = chatId || this.currentChatId;
      if (!chatId) return null;

      var cached = this.conversations[chatId];
      if (!cached) return null;

      // Check if cache is expired
      if (Date.now() - cached.timestamp > CONFIG.MAX_CACHE_AGE_MS) {
        delete this.conversations[chatId];
        return null;
      }

      return cached;
    },

    /**
     * Update conversation cache
     */
    setConversationCache: function (chatId, data) {
      if (!chatId || !data) return;

      var hash = this.generateHash(data.messages);

      this.conversations[chatId] = {
        hash: hash,
        data: data,
        timestamp: Date.now(),
        messageCount: data.messageCount || 0
      };

      // Verbose: Cache update details
      if (CONFIG.VERBOSE) {
      }
    },

    /**
     * Check if conversation has changed
     */
    hasConversationChanged: function (chatId, newData) {
      var cached = this.getConversationCache(chatId);
      if (!cached) return true; // No cache = changed

      var newHash = this.generateHash(newData.messages);
      var changed = cached.hash !== newHash;

      if (changed) {
        // Verbose: Hash change details
        if (CONFIG.VERBOSE) {
        }
      }

      return changed;
    },

    /**
     * Get sidebar cache
     */
    getSidebarCache: function () {
      if (!this.sidebar) return null;

      // Check expiry
      if (Date.now() - this.sidebar.timestamp > CONFIG.MAX_CACHE_AGE_MS) {
        this.sidebar = null;
        return null;
      }

      return this.sidebar;
    },

    /**
     * Update sidebar cache
     */
    setSidebarCache: function (data) {
      if (!data) return;

      var hash = this.generateHash(data.chats);

      this.sidebar = {
        hash: hash,
        data: data,
        timestamp: Date.now(),
        chatCount: data.totalChats || 0
      };

      // Verbose: Sidebar cache details
      if (CONFIG.VERBOSE) {
      }
    },

    /**
     * Check if sidebar has changed
     */
    hasSidebarChanged: function (newData) {
      var cached = this.getSidebarCache();
      if (!cached) return true;

      var newHash = this.generateHash(newData.chats);
      return cached.hash !== newHash;
    },

    /**
     * Register event listener
     */
    on: function (event, callback) {
      this.listeners.push({ event: event, callback: callback });
      return this.listeners.length - 1; // Return index for removal
    },

    /**
     * Remove event listener
     */
    off: function (index) {
      if (this.listeners[index]) {
        this.listeners.splice(index, 1);
      }
    },

    /**
     * Emit event to listeners
     */
    emit: function (event, data) {
      // Verbose: Event details
      if (CONFIG.VERBOSE) {
      }
      this.listeners.forEach(function (listener) {
        if (listener.event === event || listener.event === '*') {
          try {
            listener.callback(event, data);
          } catch (e) {
          }
        }
      });
    },

    /**
     * Clear all caches
     */
    clearAll: function () {
      this.conversations = {};
      this.sidebar = null;
      this.currentChatId = null;
      // Verbose: Cache clear info
      if (CONFIG.VERBOSE) {
      }
    },

    /**
     * Clear cache for specific chat
     */
    clearChat: function (chatId) {
      if (this.conversations[chatId]) {
        delete this.conversations[chatId];
        // Verbose: Cache clear details
        if (CONFIG.VERBOSE) {
        }
      }
    },

    /**
     * Get cache statistics
     */
    getStats: function () {
      var chatIds = Object.keys(this.conversations);
      return {
        conversationsCached: chatIds.length,
        cachedChatIds: chatIds,
        currentChatId: this.currentChatId,
        currentUrl: this.currentUrl,
        sidebarCached: !!this.sidebar,
        sidebarChatCount: this.sidebar ? this.sidebar.chatCount : 0,
        isStreaming: this.isStreaming,
        cacheAge: this.sidebar ? Math.round((Date.now() - this.sidebar.timestamp) / 1000) + 's' : null
      };
    }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // SESSION STORE - CUMULATIVE DATA COLLECTION (Cross-Tab Synchronized)
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * SessionStore accumulates ALL conversations visited during a session.
   * Unlike DataCache (which caches for efficiency), SessionStore PRESERVES
   * all data for export - it never deletes, only adds/updates.
   * 
   * DATA IS SYNCHRONIZED ACROSS ALL TABS using localStorage!
   */
  var STORAGE_KEY = 'velocity_chatgpt_session';

  var SessionStore = {
    // Session metadata
    sessionId: null,
    sessionStartedAt: null,

    // Accumulated conversations: { chatId: { title, messages, firstVisited, lastUpdated, ... } }
    conversations: {},

    // Order of visits (for maintaining chronological order)
    visitOrder: [],

    // Sidebar snapshot
    sidebarSnapshot: null,

    // Statistics
    stats: {
      totalChatsVisited: 0,
      totalMessagesCollected: 0,
      totalUpdates: 0
    },

    // Tab identifier
    tabId: 'tab_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),

    // OPTIMIZATION: Batched localStorage saves
    pendingSave: null,
    saveTimer: null,
    isSaving: false,

    /**
     * Initialize session - loads existing data from localStorage
     */
    init: function () {
      var self = this;

      // Try to load existing session from localStorage
      var existingData = this.loadFromStorage();

      if (existingData && existingData.sessionId) {
        // Resume existing session
        this.sessionId = existingData.sessionId;
        this.sessionStartedAt = existingData.sessionStartedAt;
        this.conversations = existingData.conversations || {};
        this.visitOrder = existingData.visitOrder || [];
        this.sidebarSnapshot = existingData.sidebarSnapshot || null;
        this.stats = existingData.stats || {
          totalChatsVisited: 0,
          totalMessagesCollected: 0,
          totalUpdates: 0
        };

        // Clean up corrupted chats if there are too many (prevents performance issues)
        this.cleanupCorruptedChats(3);

        // Check for chats with missing messages
        var self = this;
        var missingMessages = [];
        Object.keys(this.conversations).forEach(function (chatId) {
          var chat = self.conversations[chatId];
          if (chat.messageCount > 0 && (!chat.messages || chat.messages.length === 0)) {
            missingMessages.push({ chatId: chatId, title: chat.title, url: chat.url });
          }
        });

        if (missingMessages.length > 0) {
          Logger.warn('⚠️ Found ' + missingMessages.length + ' chat(s) with missing messages:');
          missingMessages.forEach(function (item) {
            Logger.warn('   • "' + item.title + '" (' + item.chatId.substring(0, 8) + '...)');
          });
          Logger.warn('   💡 To fix: Navigate to each chat and run:');
          Logger.warn('      VelocityChatGPTExtractor.session.fixMissingMessages()');
          Logger.warn('   Or: VelocityDemo.debug() to see details');
        }
      } else {
        // Start fresh session
        this.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
        this.sessionStartedAt = Date.now();
        this.conversations = {};
        this.visitOrder = [];
        this.sidebarSnapshot = null;
        this.stats = {
          totalChatsVisited: 0,
          totalMessagesCollected: 0,
          totalUpdates: 0
        };

        // Save new session
        this.saveToStorage();
        Logger.success('🆕 New session started: ' + this.sessionId);
      }

      // Listen for changes from other tabs
      this.setupCrossTabSync();
    },

    /**
     * Setup cross-tab synchronization via storage events
     */
    setupCrossTabSync: function () {
      var self = this;

      window.addEventListener('storage', function (e) {
        if (e.key === STORAGE_KEY && e.newValue) {
          try {
            var otherTabData = JSON.parse(e.newValue);

            // Only sync if it's the same session
            if (otherTabData.sessionId === self.sessionId) {
              Logger.info('🔄 Syncing data from another tab...');
              self.mergeFromOtherTab(otherTabData);
            }
          } catch (err) {
            Logger.error('Cross-tab sync error:', err);
          }
        }
      });

      // Verbose: Cross-tab sync info
      if (CONFIG.VERBOSE) {
        Logger.log('Cross-tab sync enabled (Tab ID: ' + this.tabId + ')');
      }
    },

    /**
     * Merge data received from another tab
     */
    mergeFromOtherTab: function (otherData) {
      var merged = false;
      var self = this;

      // Merge conversations
      if (otherData.conversations) {
        Object.keys(otherData.conversations).forEach(function (chatId) {
          var otherChat = otherData.conversations[chatId];
          var ourChat = self.conversations[chatId];

          if (!ourChat) {
            // New chat from other tab - add it
            self.conversations[chatId] = otherChat;
            if (self.visitOrder.indexOf(chatId) === -1) {
              self.visitOrder.push(chatId);
            }
            merged = true;
            // Verbose: Cross-tab merge details
            if (CONFIG.VERBOSE) {
              Logger.log('   + Added from other tab: ' + otherChat.title);
            }
          } else if (otherChat.messageCount > ourChat.messageCount) {
            // Other tab has more messages - update
            self.conversations[chatId] = otherChat;
            merged = true;
            // Verbose: Cross-tab merge details
            if (CONFIG.VERBOSE) {
              Logger.log('   ↑ Updated from other tab: ' + otherChat.title);
            }
          }
        });
      }

      // Update stats
      if (otherData.stats) {
        this.stats.totalChatsVisited = Math.max(this.stats.totalChatsVisited, otherData.stats.totalChatsVisited);
        this.stats.totalMessagesCollected = Math.max(this.stats.totalMessagesCollected, otherData.stats.totalMessagesCollected);
        this.stats.totalUpdates = Math.max(this.stats.totalUpdates, otherData.stats.totalUpdates);
      }

      // Update sidebar if newer
      if (otherData.sidebarSnapshot &&
        (!this.sidebarSnapshot || otherData.sidebarSnapshot.updatedAt > this.sidebarSnapshot.updatedAt)) {
        this.sidebarSnapshot = otherData.sidebarSnapshot;
      }

      if (merged) {
        Logger.success('✅ Merged data from other tab');
      }
    },

    /**
     * Queue save for next idle period (OPTIMIZATION: Non-blocking)
     */
    queueSave: function () {
      var self = this;

      // Clear existing timer
      if (this.saveTimer) {
        if (window.cancelIdleCallback) {
          window.cancelIdleCallback(this.saveTimer);
        } else {
          clearTimeout(this.saveTimer);
        }
        this.saveTimer = null;
      }

      // Queue save for next idle period
      if (window.requestIdleCallback) {
        this.saveTimer = window.requestIdleCallback(function () {
          self.saveToStorage();
        }, { timeout: 2000 }); // Max 2s delay
      } else {
        // Fallback: debounce with setTimeout
        this.saveTimer = setTimeout(function () {
          self.saveToStorage();
        }, 1000);
      }
    },

    /**
     * Save current session to localStorage (with compression)
     * OPTIMIZED: Uses setTimeout to yield to main thread
     */
    saveToStorage: function () {
      var self = this;

      if (this.isSaving) {
        // Already saving, queue next save
        this.queueSave();
        return;
      }

      this.isSaving = true;

      // Use setTimeout to yield to main thread (non-blocking)
      setTimeout(function () {
        try {
          // Prepare data with compressed messages
          var compressedConversations = {};

          Object.keys(self.conversations).forEach(function (chatId) {
            var chat = self.conversations[chatId];

            // VALIDATION: Ensure messages is an array before stringifying
            var messagesToStore = Array.isArray(chat.messages) ? chat.messages : [];

            // Compress message content
            var messagesJson = JSON.stringify(messagesToStore);
            var contentHash = Compression.generateHash(messagesJson);

            var compressedMessages = null;
            var isCompressed = false;

            if (CONFIG.COMPRESS_STORAGE && messagesJson.length > 100) {
              // Only compress if data is large enough
              try {
                compressedMessages = Compression.compress(messagesJson);
                isCompressed = true;
              } catch (e) {
                Logger.warn('Compression failed for chat ' + chatId.substring(0, 8) + ', storing uncompressed');
                compressedMessages = messagesJson;
                isCompressed = false;
              }
            } else {
              // Store directly if small or compression disabled
              compressedMessages = messagesJson;
              isCompressed = false;
            }

            compressedConversations[chatId] = {
              chatId: chat.chatId,
              title: chat.title,
              url: chat.url,
              firstVisited: chat.firstVisited,
              lastUpdated: chat.lastUpdated,
              visitCount: chat.visitCount,
              messageCount: chat.messageCount,
              // Store messages (compressed or not) + hash
              messagesCompressed: compressedMessages,
              contentHash: contentHash,
              isCompressed: isCompressed,
              richContentSummary: chat.richContentSummary,
              // Also store messages directly as fallback (for small chats)
              messages: isCompressed ? null : (chat.messages || [])
            };
          });

          var data = {
            sessionId: self.sessionId,
            sessionStartedAt: self.sessionStartedAt,
            conversations: compressedConversations,
            visitOrder: self.visitOrder,
            sidebarSnapshot: self.sidebarSnapshot,
            stats: self.stats,
            lastUpdated: Date.now(),
            lastUpdatedBy: self.tabId,
            compressed: CONFIG.COMPRESS_STORAGE
          };

          var jsonStr = JSON.stringify(data);
          localStorage.setItem(STORAGE_KEY, jsonStr);

          // Verbose: Storage save details
          if (CONFIG.VERBOSE) {
            Logger.log('Saved to storage (' + Math.round(jsonStr.length / 1024) + ' KB)');
          }
        } catch (err) {
          Logger.error('Failed to save to localStorage:', err);
        } finally {
          self.isSaving = false;
        }
      }, 0); // Yield to main thread immediately
    },

    /**
     * Load session from localStorage (with decompression)
     */
    loadFromStorage: function () {
      try {
        var data = localStorage.getItem(STORAGE_KEY);
        if (data) {
          var parsed = JSON.parse(data);

          // Check if session is not too old (24 hours max)
          var maxAge = 24 * 60 * 60 * 1000; // 24 hours
          if (parsed.sessionStartedAt && (Date.now() - parsed.sessionStartedAt) > maxAge) {
            Logger.log('Previous session expired, starting fresh');
            localStorage.removeItem(STORAGE_KEY);
            return null;
          }

          // Decompress conversations
          if (parsed.conversations) {
            var self = this;
            var corruptedChats = [];
            Object.keys(parsed.conversations).forEach(function (chatId) {
              var chat = parsed.conversations[chatId];

              // Skip if already marked as corrupted
              if (chat._corrupted) {
                corruptedChats.push(chatId);
                return;
              }

              // Priority 1: Use direct messages if available (fallback for small/uncompressed chats)
              if (chat.messages && Array.isArray(chat.messages) && chat.messages.length > 0) {
                // Already decompressed or never compressed
                if (CONFIG.VERBOSE) {
                  Logger.log('Chat ' + chatId.substring(0, 8) + ' has direct messages (' + chat.messages.length + ')');
                }
              }
              // Priority 2: Decompress from compressed storage
              else if (chat.messagesCompressed) {
                try {
                  // Decompress messages
                  var messagesJson = chat.isCompressed ?
                    Compression.decompress(chat.messagesCompressed) :
                    chat.messagesCompressed;

                  if (messagesJson) {
                    // Try to parse JSON with better error handling
                    try {
                      chat.messages = JSON.parse(messagesJson);

                      // Validate hash
                      if (chat.contentHash) {
                        var isValid = Compression.validate(chat.messages, chat.contentHash);
                        if (!isValid) {
                          if (CONFIG.VERBOSE) {
                            Logger.warn('Hash mismatch for chat: ' + chatId.substring(0, 8) + ' - data may be corrupted');
                          }
                        } else {
                          if (CONFIG.VERBOSE) {
                            Logger.log('Chat ' + chatId.substring(0, 8) + ' decompressed and validated (' + chat.messages.length + ' msgs)');
                          }
                        }
                      }
                    } catch (parseError) {
                      // JSON parsing failed - mark as corrupted and skip
                      Logger.warn('Failed to parse decompressed JSON for chat: ' + chatId.substring(0, 8) + ' - marking as corrupted');
                      chat._corrupted = true;
                      chat.messages = [];
                      corruptedChats.push(chatId);
                    }
                  } else {
                    if (CONFIG.VERBOSE) {
                      Logger.warn('Empty decompressed data for chat: ' + chatId.substring(0, 8));
                    }
                    chat.messages = [];
                  }
                } catch (e) {
                  // Decompression failed - mark as corrupted and skip to prevent repeated attempts
                  if (CONFIG.VERBOSE) {
                    Logger.error('Failed to decompress chat: ' + chatId.substring(0, 8), e);
                  }
                  chat._corrupted = true;
                  chat.messages = [];
                  corruptedChats.push(chatId);
                }
              } else {
                // No messages and no compressed data - might be old format
                if (CONFIG.VERBOSE) {
                  Logger.warn('Chat ' + chatId.substring(0, 8) + ' has no message data');
                }
                chat.messages = chat.messages || [];
              }
            });

            // Clean up corrupted chats if there are too many (to prevent storage bloat)
            if (corruptedChats.length > 0) {
              if (corruptedChats.length <= 3) {
                // Only log if a few chats are corrupted
                Logger.warn('⚠️ Found ' + corruptedChats.length + ' corrupted chat(s) - they will be skipped');
              } else {
                // If many are corrupted, clean them up
                Logger.warn('⚠️ Found ' + corruptedChats.length + ' corrupted chats - cleaning up to prevent performance issues');
                corruptedChats.forEach(function (chatId) {
                  delete parsed.conversations[chatId];
                });
                // Save cleaned data back
                try {
                  localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
                } catch (e) {
                  // Ignore save errors
                }
              }
            }
          }

          return parsed;
        }
      } catch (err) {
        Logger.error('Failed to load from localStorage:', err);
      }
      return null;
    },

    /**
     * Clean up corrupted chats from storage
     * @param {number} maxCorrupted - Maximum number of corrupted chats to keep before cleanup
     * @returns {number} Number of chats cleaned up
     */
    cleanupCorruptedChats: function (maxCorrupted) {
      maxCorrupted = maxCorrupted || 3;
      try {
        var data = localStorage.getItem(STORAGE_KEY);
        if (!data) return 0;

        var parsed = JSON.parse(data);
        if (!parsed.conversations) return 0;

        var corruptedChats = [];
        Object.keys(parsed.conversations).forEach(function (chatId) {
          var chat = parsed.conversations[chatId];
          if (chat._corrupted) {
            corruptedChats.push(chatId);
          }
        });

        if (corruptedChats.length > maxCorrupted) {
          // Remove all corrupted chats if there are too many
          corruptedChats.forEach(function (chatId) {
            delete parsed.conversations[chatId];
            // Also remove from visitOrder
            var index = parsed.visitOrder.indexOf(chatId);
            if (index > -1) {
              parsed.visitOrder.splice(index, 1);
            }
          });

          // Save cleaned data
          localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));

          // Update in-memory state
          this.conversations = parsed.conversations;
          this.visitOrder = parsed.visitOrder;

          Logger.warn('🧹 Cleaned up ' + corruptedChats.length + ' corrupted chats to improve performance');
          return corruptedChats.length;
        }

        return 0;
      } catch (e) {
        Logger.error('Failed to cleanup corrupted chats:', e);
        return 0;
      }
    },

    /**
     * Add or update a conversation in the store
     * @param {string} chatId - The chat ID
     * @param {Object} data - Conversation data from extraction
     * @returns {Object} Update result with what changed
     */
    upsertConversation: function (chatId, data) {
      if (!chatId || !data) return { action: 'skipped', reason: 'invalid data', chatId: chatId, sessionId: chatId };

      // Validate that we have messages to store
      var messages = data.messages || [];
      var messageCount = data.messageCount || messages.length;

      if (messageCount > 0 && messages.length === 0) {
        Logger.warn('⚠️ Chat has messageCount=' + messageCount + ' but messages array is empty!');
        Logger.warn('   This might be a timing issue - extraction may not be complete yet.');
        // Don't skip, but log the issue
      }

      var existing = this.conversations[chatId];
      var now = Date.now();

      if (!existing) {
        // NEW CHAT - Only add if it has actual messages
        // Skip empty chats to avoid storing multiple empty conversations

        // Check if chat has any messages
        var hasMessages = messages.length > 0 || messageCount > 0;

        if (!hasMessages) {
          // Empty chat - don't store yet, wait until user starts chatting
          // Verbose: Empty chat skip
          if (CONFIG.VERBOSE) {
            Logger.log('⏭️ Skipping empty chat (no messages yet): ' + chatId.substring(0, 8));
            Logger.log('   Will store once user starts chatting');
          }
          return {
            action: 'skipped',
            reason: 'empty_chat',
            chatId: chatId,
            sessionId: chatId, // Add sessionId for consistency
            messageCount: 0
          };
        }

        // Chat has messages - proceed with storage
        if (messages.length === 0 && messageCount > 0) {
          Logger.warn('⚠️ Chat ' + chatId.substring(0, 8) + ' has count=' + messageCount + ' but no messages yet');
          Logger.warn('   Saving anyway - will auto-fix on next visit');
        }

        // VALIDATION: Ensure messages is a valid array
        var validMessages = Array.isArray(messages) ? messages : [];

        // VALIDATION: Ensure messageCount matches actual messages
        var actualMessageCount = validMessages.length > 0 ? validMessages.length : messageCount;

        this.conversations[chatId] = {
          chatId: chatId,
          title: this.extractTitle(chatId, data) || 'Untitled Chat',
          url: data.url || window.location.href,
          firstVisited: now,
          lastUpdated: now,
          visitCount: 1,
          messageCount: actualMessageCount,
          messages: validMessages, // Always store as array (empty if no messages)
          richContentSummary: data.richContentSummary || null
        };

        // Add to visit order
        this.visitOrder.push(chatId);
        this.stats.totalChatsVisited++;
        this.stats.totalMessagesCollected += messageCount;

        // Show important: New chat added
        Logger.success('📥 NEW chat added: ' + this.conversations[chatId].title + ' (' + messageCount + ' messages)');
        // Verbose: Chat details
        if (CONFIG.VERBOSE) {
          Logger.log('   Chat ID: ' + chatId);
          Logger.log('   Messages: ' + messageCount + ' (stored: ' + messages.length + ')');
        }

        // Queue save to localStorage for cross-tab sync (non-blocking)
        this.queueSave();

        return {
          action: 'added',
          chatId: chatId,
          sessionId: chatId, // Add sessionId for consistency
          title: this.conversations[chatId].title,
          messageCount: data.messageCount
        };

      } else {
        // EXISTING CHAT - Check for updates
        var oldMessageCount = existing.messageCount;
        var newMessageCount = data.messageCount || 0;

        // Check if we need to fix missing messages or update
        var hasEmptyMessages = (!existing.messages || existing.messages.length === 0) && existing.messageCount > 0;
        var hasNewMessages = newMessageCount > oldMessageCount;
        var hasMessageData = data.messages && data.messages.length > 0;

        // Calculate new messages (if we have message data)
        var newMessages = [];
        if (hasMessageData && hasNewMessages && existing.messages && existing.messages.length > 0) {
          // Extract only the new messages (messages after the old count)
          newMessages = data.messages.slice(oldMessageCount);
        } else if (hasMessageData && hasEmptyMessages) {
          // All messages are new (was empty before)
          newMessages = data.messages;
        }

        // ALWAYS update if we have message data (fixing missing or new messages)
        if (hasMessageData) {
          // VALIDATION: Ensure messages is a valid array
          var validMessages = Array.isArray(data.messages) ? data.messages : [];

          // We have message data - ALWAYS save it (fixes missing messages or adds new ones)
          existing.messages = validMessages;
          existing.messageCount = Math.max(newMessageCount, validMessages.length); // Use actual count
          existing.lastUpdated = now;
          existing.visitCount++;
          existing.richContentSummary = data.richContentSummary || existing.richContentSummary;

          if (hasEmptyMessages) {
            Logger.success('✅ FIXED missing messages for chat: ' + existing.title + ' (' + data.messages.length + ' msgs)');
          } else if (hasNewMessages) {
            Logger.success('✅ UPDATED chat: ' + existing.title + ' (now ' + data.messages.length + ' msgs)');
          } else {
            // Verbose: Message refresh
            if (CONFIG.VERBOSE) {
              Logger.log('✅ Messages refreshed for chat: ' + existing.title);
            }
          }

          this.stats.totalMessagesCollected += (newMessageCount - oldMessageCount);
          this.stats.totalUpdates++;

          // Queue save to localStorage for cross-tab sync (non-blocking)
          this.queueSave();

          return {
            action: 'updated',
            chatId: chatId,
            sessionId: chatId, // Add sessionId for consistency
            title: existing.title,
            previousCount: oldMessageCount,
            newCount: newMessageCount,
            addedMessages: newMessageCount - oldMessageCount,
            newMessages: newMessages
          };
        } else if (hasNewMessages || hasEmptyMessages) {
          // Message count changed but no message data yet - update metadata but keep existing messages
          existing.messageCount = Math.max(newMessageCount, existing.messageCount);
          existing.lastUpdated = now;
          existing.visitCount++;
          existing.richContentSummary = data.richContentSummary || existing.richContentSummary;

          if (hasEmptyMessages) {
            Logger.warn('⚠️ Chat ' + chatId.substring(0, 8) + ' still has empty messages (expected: ' + existing.messageCount + ')');
            Logger.warn('   Will retry on next visit...');
          }

          this.stats.totalMessagesCollected += (newMessageCount - oldMessageCount);
          this.stats.totalUpdates++;

          Logger.success('📝 Chat UPDATED: ' + existing.title);
          Logger.log('   New messages: +' + (newMessageCount - oldMessageCount));
          Logger.log('   Total now: ' + newMessageCount);

          // Queue save to localStorage for cross-tab sync (non-blocking)
          this.queueSave();

          return {
            action: 'updated',
            chatId: chatId,
            sessionId: chatId, // Add sessionId for consistency
            title: existing.title,
            previousCount: oldMessageCount,
            newCount: newMessageCount,
            addedMessages: newMessageCount - oldMessageCount,
            newMessages: newMessages // Empty array since we don't have message data yet
          };

        } else {
          // No new messages - just update visit count
          existing.visitCount++;
          existing.lastUpdated = now;

          // Verbose: Chat revisit
          if (CONFIG.VERBOSE) {
            Logger.log('👁️ Chat revisited (no new messages): ' + existing.title);
          }

          return {
            action: 'unchanged',
            chatId: chatId,
            title: existing.title,
            messageCount: existing.messageCount
          };
        }
      }
    },

    /**
     * Extract title from sidebar or generate from first message
     */
    extractTitle: function (chatId, data) {
      // Try to get from sidebar cache
      if (DataCache.sidebar && DataCache.sidebar.data && DataCache.sidebar.data.chats) {
        var sidebarChat = DataCache.sidebar.data.chats.find(function (c) {
          return c.chatId === chatId;
        });
        if (sidebarChat && sidebarChat.title) {
          return sidebarChat.title;
        }
      }

      // Generate from first user message
      if (data.messages && data.messages.length > 0) {
        var firstUserMsg = data.messages.find(function (m) { return m.role === 'user'; });
        if (firstUserMsg && firstUserMsg.content) {
          var title = firstUserMsg.content.substring(0, 50);
          if (firstUserMsg.content.length > 50) title += '...';
          return title;
        }
      }

      return 'Chat ' + chatId.substring(0, 8);
    },

    /**
     * Update sidebar snapshot
     */
    updateSidebar: function (data) {
      if (!data || !data.chats) return;

      this.sidebarSnapshot = {
        updatedAt: Date.now(),
        totalChats: data.totalChats || data.chats.length,
        chats: data.chats
      };

      // Queue save to localStorage for cross-tab sync (non-blocking)
      this.queueSave();

      Logger.log('Sidebar snapshot updated: ' + this.sidebarSnapshot.totalChats + ' chats');
    },

    /**
     * Get a specific conversation from the store
     */
    getConversation: function (chatId) {
      return this.conversations[chatId] || null;
    },

    /**
     * Get stored content for enhancement (validates hash)
     * This returns the STORED content, not fresh extraction
     * @param {string} chatId - Chat ID (optional, defaults to current)
     * @returns {Object} Content with validation status
     */
    getStoredContentForEnhance: function (chatId) {
      chatId = chatId || DataCache.getChatIdFromUrl();

      if (!chatId) {
        return {
          success: false,
          error: 'No chat ID provided or detected',
          data: null
        };
      }

      var chat = this.conversations[chatId];

      if (!chat) {
        return {
          success: false,
          error: 'Chat not found in session: ' + chatId,
          data: null
        };
      }

      // Validate hash if available
      var isValid = true;
      if (chat.contentHash && chat.messages) {
        isValid = Compression.validate(chat.messages, chat.contentHash);
      }

      return {
        success: true,
        validated: isValid,
        contentHash: chat.contentHash,
        data: {
          chatId: chat.chatId,
          title: chat.title,
          url: chat.url,
          messageCount: chat.messageCount,
          messages: chat.messages,
          richContentSummary: chat.richContentSummary,
          firstVisited: chat.firstVisited,
          lastUpdated: chat.lastUpdated
        }
      };
    },

    /**
     * Get ALL stored content for enhancement (all chats)
     * Returns stored data, not fresh extraction
     * @returns {Object} All session data with validation
     */
    getAllStoredContentForEnhance: function () {
      var self = this;
      var allChats = [];
      var allValid = true;
      var invalidChats = [];

      this.visitOrder.forEach(function (chatId) {
        var result = self.getStoredContentForEnhance(chatId);
        if (result.success) {
          allChats.push(result.data);
          if (!result.validated) {
            allValid = false;
            invalidChats.push(chatId);
          }
        }
      });

      return {
        success: true,
        validated: allValid,
        invalidChats: invalidChats,
        sessionId: this.sessionId,
        totalChats: allChats.length,
        totalMessages: this.stats.totalMessagesCollected,
        data: {
          sessionId: this.sessionId,
          sessionStartedAt: this.sessionStartedAt,
          conversations: allChats,
          stats: this.stats,
          sidebar: this.sidebarSnapshot
        }
      };
    },

    /**
     * Get all conversations as an array (in visit order)
     */
    getAllConversations: function () {
      var self = this;
      return this.visitOrder.map(function (chatId) {
        var chat = self.conversations[chatId];
        if (!chat) return null;

        // Clone to avoid mutating original
        var exported = Object.assign({}, chat);

        // Ensure messages are decompressed
        if (!exported.messages || exported.messages.length === 0) {
          if (exported.messagesCompressed) {
            try {
              var messagesJson = exported.isCompressed ?
                Compression.decompress(exported.messagesCompressed) :
                exported.messagesCompressed;
              if (messagesJson) {
                exported.messages = JSON.parse(messagesJson);
              }
            } catch (e) {
              Logger.warn('Failed to decompress messages for chat: ' + chatId.substring(0, 8));
              exported.messages = [];
            }
          } else {
            exported.messages = [];
          }
        }

        // Remove compressed fields from export (user wants clean JSON)
        delete exported.messagesCompressed;
        delete exported.contentHash;
        delete exported.isCompressed;

        return exported;
      }).filter(Boolean);
    },

    /**
     * Extract user info from Chrome Storage (Velocity extension)
     * This is async because chrome.storage.local.get() is async
     */
    extractUserInfoFromChromeStorage: function (callback) {
      // Helper to unwrap stringified values
      function unwrapValue(value) {
        if (!value || typeof value !== 'string') return value;
        if (value.startsWith('"') && value.endsWith('"')) {
          try {
            var parsed = JSON.parse(value);
            if (typeof parsed === 'string') return unwrapValue(parsed);
            return parsed;
          } catch (e) {
            return value;
          }
        }
        return value;
      }

      // Helper to get from localStorage as fallback
      function getFromLocalStorage(key) {
        try {
          if (typeof localStorage === 'undefined') return null;
          var value = localStorage.getItem(key);
          if (!value) return null;
          return unwrapValue(value);
        } catch (e) {
          return null;
        }
      }

      // Try Chrome storage first
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        try {
          chrome.storage.local.get([
            'userId',
            'userName',
            'userEmail',
            'remainingUsage',
            'usageLimit',
            'userStatus',
            'velocity_user_mode',
          ], function (result) {
            if (chrome.runtime.lastError) {
              Logger.warn('Failed to read Chrome storage:', chrome.runtime.lastError);
              // Fallback to localStorage
              var fallbackData = {
                user_id: getFromLocalStorage('userId'),
                userId: getFromLocalStorage('userId'),
                name: getFromLocalStorage('userName'),
                email: getFromLocalStorage('userEmail'),
                usage_left: getFromLocalStorage('remainingUsage'),
                remainingUsage: getFromLocalStorage('remainingUsage'),
                status: null,
              };
              if (callback) callback(fallbackData);
              return;
            }
            // Also try to get non-sensitive user fields from localStorage as fallback.
            var userId = result.userId || getFromLocalStorage('userId') || null;
            var userName = result.userName || getFromLocalStorage('userName') || null;
            var userEmail = result.userEmail || getFromLocalStorage('userEmail') || null;
            var remainingUsage = result.remainingUsage || result.usageLimit || getFromLocalStorage('remainingUsage') || null;

            var chromeData = {
              user_id: userId,
              userId: userId,
              name: userName,
              email: userEmail,
              usage_left: remainingUsage,
              remainingUsage: remainingUsage,
              status: result.velocity_user_mode || (result.userStatus && result.userStatus.status) || null,
              userStatus: result.userStatus || null,
            };

            Logger.log('Extracted user data from Chrome storage:', {
              hasUserId: !!chromeData.userId,
              hasEmail: !!chromeData.email
            });

            if (callback) callback(chromeData);
          });
        } catch (e) {
          Logger.warn('Error accessing Chrome storage:', e);
          // Fallback to localStorage
          var fallbackData = {
            user_id: getFromLocalStorage('userId'),
            userId: getFromLocalStorage('userId'),
            name: getFromLocalStorage('userName'),
            email: getFromLocalStorage('userEmail'),
            usage_left: getFromLocalStorage('remainingUsage'),
            remainingUsage: getFromLocalStorage('remainingUsage'),
            status: null,
          };
          if (callback) callback(fallbackData);
        }
      } else {
        // Chrome storage not available, try localStorage only
        Logger.warn('Chrome storage API not available, using localStorage fallback');
        var fallbackData = {
          user_id: getFromLocalStorage('userId'),
          userId: getFromLocalStorage('userId'),
          name: getFromLocalStorage('userName'),
          email: getFromLocalStorage('userEmail'),
          usage_left: getFromLocalStorage('remainingUsage'),
          remainingUsage: getFromLocalStorage('remainingUsage'),
          status: null,
        };
        if (callback) callback(fallbackData);
      }
    },

    /**
     * Extract user info, auth token, and trial info from ChatGPT
     */
    extractUserInfo: function () {
      var userInfo = {
        userId: null,
        user_id: null,  // Alias for userId
        email: null,
        name: null,
        picture: null,
        status: null,
        usage_left: null,
        trialLeft: null,
        subscription: null,
        plan: null,
        connectionType: null
      };

      // Helper to decode URL-encoded JSON
      function tryDecodeJson(str) {
        if (!str || typeof str !== 'string') return null;
        try {
          // Try direct JSON parse first
          return JSON.parse(str);
        } catch (e1) {
          try {
            // Try URL decode then parse
            var decoded = decodeURIComponent(str);
            return JSON.parse(decoded);
          } catch (e2) {
            return null;
          }
        }
      }

      // Helper to extract user from nested object
      function extractUserData(obj, path) {
        if (!obj || typeof obj !== 'object') return null;
        var parts = path.split('.');
        var current = obj;
        for (var i = 0; i < parts.length; i++) {
          if (current && typeof current === 'object' && current[parts[i]] !== undefined) {
            current = current[parts[i]];
          } else {
            return null;
          }
        }
        return current;
      }

      try {
        // Method 1: Check localStorage
        try {
          var localStorageKeys = Object.keys(localStorage);
          for (var i = 0; i < localStorageKeys.length; i++) {
            var key = localStorageKeys[i];
            var value = localStorage.getItem(key);

            if (!value) continue;

            // Look for user/auth/token keys
            if (key.indexOf('user') !== -1 || key.indexOf('auth') !== -1 || key.indexOf('token') !== -1 ||
              key.indexOf('openai') !== -1 || key.indexOf('chatgpt') !== -1) {

              // Try to parse as JSON (handles URL-encoded JSON)
              var parsed = tryDecodeJson(value);

              if (parsed && typeof parsed === 'object') {
                // Extract user data from various structures
                var user = extractUserData(parsed, 'user') ||
                  extractUserData(parsed, 'data.user') ||
                  extractUserData(parsed, 'payload.user') ||
                  parsed;

                if (user && typeof user === 'object') {
                  if (user.id || user.userId || user.user_id) {
                    var uid = user.id || user.userId || user.user_id;
                    userInfo.userId = uid;
                    userInfo.user_id = uid;  // Set both
                    Logger.log('[ChatGPT Extractor] ✅ User identified via localStorage key "' + key + '": ' + uid);
                  }
                  if (user.email) userInfo.email = user.email;
                  if (user.name || user.full_name || user.displayName) {
                    userInfo.name = user.name || user.full_name || user.displayName;
                  }
                  if (user.picture || user.avatar || user.avatar_url) {
                    userInfo.picture = user.picture || user.avatar || user.avatar_url;
                  }
                  if (user.status || user.accountStatus || user.account_status) {
                    userInfo.status = user.status || user.accountStatus || user.account_status;
                  }
                  if (user.usage_left !== undefined || user.usageLeft !== undefined || user.usage !== undefined) {
                    var usage = user.usage_left !== undefined ? user.usage_left :
                      (user.usageLeft !== undefined ? user.usageLeft : user.usage);
                    userInfo.usage_left = usage;
                  }
                  if (user.connectionType !== undefined) {
                    userInfo.connectionType = user.connectionType;
                  }
                }

                // Extract subscription/trial info
                var subscription = extractUserData(parsed, 'subscription') ||
                  extractUserData(parsed, 'user.subscription') ||
                  extractUserData(parsed, 'data.subscription');

                if (subscription) {
                  userInfo.subscription = subscription;
                  if (subscription.plan) userInfo.plan = subscription.plan;
                  if (subscription.trialLeft !== undefined) {
                    userInfo.trialLeft = subscription.trialLeft;
                  }
                }
              } else if (typeof value === 'string') {
                // Not JSON - might be a direct token
                // Check if it's URL-encoded JSON and decode it
                if (value.startsWith('%7B') || value.indexOf('%22') !== -1) {
                  // Looks like URL-encoded JSON
                  try {
                    var decoded = decodeURIComponent(value);
                    var decodedParsed = JSON.parse(decoded);
                    if (decodedParsed && typeof decodedParsed === 'object') {
                      var decodedUser = extractUserData(decodedParsed, 'user') || decodedParsed;
                      if (decodedUser && typeof decodedUser === 'object') {
                        if (decodedUser.email) userInfo.email = decodedUser.email;
                        if (decodedUser.name) userInfo.name = decodedUser.name;
                        if (decodedUser.picture) userInfo.picture = decodedUser.picture;
                        if (decodedUser.status || decodedUser.accountStatus) {
                          userInfo.status = decodedUser.status || decodedUser.accountStatus;
                        }
                        if (decodedUser.usage_left !== undefined || decodedUser.usageLeft !== undefined) {
                          var usage = decodedUser.usage_left !== undefined ? decodedUser.usage_left : decodedUser.usageLeft;
                          userInfo.usage_left = usage;
                        }
                        if (decodedUser.connectionType !== undefined) {
                          userInfo.connectionType = decodedUser.connectionType;
                        }
                      }
                    }
                  } catch (e) {
                    // Not decodable, skip
                  }
                }
              }
            }
          }
        } catch (e) {
          Logger.warn('Failed to read localStorage:', e);
        }

        // Method 2: Check sessionStorage
        try {
          var sessionKeys = Object.keys(sessionStorage);
          for (var j = 0; j < sessionKeys.length; j++) {
            var sKey = sessionKeys[j];
            var sValue = sessionStorage.getItem(sKey);

            if (sKey.indexOf('user') !== -1 || sKey.indexOf('auth') !== -1 || sKey.indexOf('token') !== -1) {
              try {
                var sParsed = JSON.parse(sValue);
                if (sParsed && typeof sParsed === 'object') {
                  if (sParsed.id || sParsed.userId) userInfo.userId = sParsed.id || sParsed.userId;
                  if (sParsed.email) userInfo.email = sParsed.email;
                }
              } catch (e) {
              }
            }
          }
        } catch (e) {
          Logger.warn('Failed to read sessionStorage:', e);
        }

        // Method 3: Check window object (ChatGPT might expose user data)
        try {
          if (window.__NEXT_DATA__) {
            var nextData = window.__NEXT_DATA__;

            // Try various paths in __NEXT_DATA__
            var userPaths = [
              'props.pageProps.user',
              'props.initialState.user',
              'props.user',
              'props.pageProps.session.user', // New path for modern ChatGPT versions
              'buildId' // Sometimes user is at root
            ];

            for (var p = 0; p < userPaths.length; p++) {
              var user = extractUserData(nextData, userPaths[p]);
              if (user && typeof user === 'object') {
                if (user.id || user.userId || user.user_id) {
                  var uid = user.id || user.userId || user.user_id;
                  userInfo.userId = uid;
                  userInfo.user_id = uid;  // Set both
                  Logger.log('[ChatGPT Extractor] ✅ User identified via __NEXT_DATA__ path "' + userPaths[p] + '": ' + uid);
                }
                if (user.email) userInfo.email = user.email;
                if (user.name || user.displayName) {
                  userInfo.name = user.name || user.displayName;
                }
                if (user.picture || user.avatar) {
                  userInfo.picture = user.picture || user.avatar;
                }
                if (user.status || user.accountStatus || user.account_status) {
                  userInfo.status = user.status || user.accountStatus || user.account_status;
                }
                if (user.usage_left !== undefined || user.usageLeft !== undefined || user.usage !== undefined) {
                  var usage = user.usage_left !== undefined ? user.usage_left :
                    (user.usageLeft !== undefined ? user.usageLeft : user.usage);
                  userInfo.usage_left = usage;
                }
                if (user.subscription) {
                  userInfo.subscription = user.subscription;
                  if (user.subscription.plan) userInfo.plan = user.subscription.plan;
                  if (user.subscription.trialLeft !== undefined) {
                    userInfo.trialLeft = user.subscription.trialLeft;
                  }
                  // Check for usage in subscription
                  if (user.subscription.usage_left !== undefined || user.subscription.usageLeft !== undefined) {
                    var subUsage = user.subscription.usage_left !== undefined ?
                      user.subscription.usage_left : user.subscription.usageLeft;
                    if (userInfo.usage_left === null) {
                      userInfo.usage_left = subUsage;
                    }
                  }
                }
                break;
              }
            }
          }
        } catch (e) {
          Logger.warn('Failed to read window.__NEXT_DATA__:', e);
        }

        // Method 3.2: Check meta tags for user-id
        try {
          var metaTag = document.querySelector('meta[name="user-id"]');
          if (metaTag && metaTag.content) {
            var metaUserId = metaTag.content.trim();
            if (metaUserId && !userInfo.user_id) {
              userInfo.userId = metaUserId;
              userInfo.user_id = metaUserId;
              Logger.log('[ChatGPT Extractor] ✅ User identified via meta tag: ' + metaUserId);
            }
          }
        } catch (e) {
          Logger.warn('Failed to read meta tags:', e);
        }

        // Method 3.3: Check specific localStorage keys for user ID
        try {
          var specificUserKeys = ['userId', 'user_id', 'chatgpt_user_id', 'chatgpt_userId'];
          for (var suk = 0; suk < specificUserKeys.length; suk++) {
            var storedUserId = localStorage.getItem(specificUserKeys[suk]);
            if (storedUserId && storedUserId.trim() && !userInfo.user_id) {
              // Try to parse as JSON first
              var parsedUserId = tryDecodeJson(storedUserId);
              if (parsedUserId && typeof parsedUserId === 'object') {
                var uid = parsedUserId.id || parsedUserId.userId || parsedUserId.user_id || parsedUserId;
                if (typeof uid === 'string' && uid.trim()) {
                  userInfo.userId = uid.trim();
                  userInfo.user_id = uid.trim();
                  Logger.log('[ChatGPT Extractor] ✅ User identified via localStorage key "' + specificUserKeys[suk] + '": ' + uid.trim());
                  break;
                }
              } else if (typeof storedUserId === 'string' && storedUserId.trim()) {
                userInfo.userId = storedUserId.trim();
                userInfo.user_id = storedUserId.trim();
                Logger.log('[ChatGPT Extractor] ✅ User identified via localStorage key "' + specificUserKeys[suk] + '": ' + storedUserId.trim());
                break;
              }
            }
          }
        } catch (e) {
          Logger.warn('Failed to check specific localStorage user keys:', e);
        }

        // Method 3.5: Check for React/Redux state
        try {
          if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__) {
            // Try to find user in React state
            var reactRoot = document.querySelector('#__next') || document.body;
            if (reactRoot && reactRoot._reactInternalFiber) {
              // This is complex, skip for now
            }
          }
        } catch (e) { }

        // Method 6: Check for trial/subscription/usage info in ChatGPT's data
        try {
          // Look for subscription data in localStorage
          var subKeys = ['subscription', 'plan', 'trial', 'usage', 'billing', 'account', 'user_status',
            'account_status', 'user_status', 'status', 'usage_left', 'usageLeft', 'remaining'];
          for (var sk = 0; sk < subKeys.length; sk++) {
            try {
              var subValue = localStorage.getItem(subKeys[sk]);
              if (subValue) {
                var subParsed = tryDecodeJson(subValue);
                if (subParsed && typeof subParsed === 'object') {
                  if (subParsed.trialLeft !== undefined && userInfo.trialLeft === null) {
                    userInfo.trialLeft = subParsed.trialLeft;
                  }
                  if (subParsed.plan && !userInfo.plan) {
                    userInfo.plan = subParsed.plan;
                  }
                  if (subParsed.status || subParsed.accountStatus || subParsed.account_status) {
                    if (!userInfo.status) {
                      userInfo.status = subParsed.status || subParsed.accountStatus || subParsed.account_status;
                    }
                  }
                  if (subParsed.usage_left !== undefined || subParsed.usageLeft !== undefined || subParsed.usage !== undefined) {
                    var usage = subParsed.usage_left !== undefined ? subParsed.usage_left :
                      (subParsed.usageLeft !== undefined ? subParsed.usageLeft : subParsed.usage);
                    if (userInfo.usage_left === null) {
                      userInfo.usage_left = usage;
                    }
                  }
                  if (subParsed.subscription && !userInfo.subscription) {
                    userInfo.subscription = subParsed.subscription;
                    // Extract usage from subscription object
                    if (subParsed.subscription.usage_left !== undefined || subParsed.subscription.usageLeft !== undefined) {
                      var subUsage = subParsed.subscription.usage_left !== undefined ?
                        subParsed.subscription.usage_left : subParsed.subscription.usageLeft;
                      if (userInfo.usage_left === null) {
                        userInfo.usage_left = subUsage;
                      }
                    }
                  }
                  // Check for user_id in subscription/account data
                  if ((subParsed.user_id || subParsed.userId || subParsed.id) && !userInfo.user_id) {
                    var uid = subParsed.user_id || subParsed.userId || subParsed.id;
                    userInfo.userId = uid;
                    userInfo.user_id = uid;
                  }
                }
              }
            } catch (e) { }
          }
        } catch (e) { }

        // Method 7: Check Chrome Storage (Velocity extension storage) - SYNC VERSION
        // Note: Chrome storage is async, so we'll try to get it but it might not be available immediately
        // The async version extractUserInfoFromChromeStorage() should be used for complete data
        try {
          // Try to access chrome.storage synchronously (won't work, but check if available)
          if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
            // Chrome storage is async, so we can't read it synchronously here
            // But we'll note that it's available for the async method
            Logger.log('Chrome storage API available (use extractUserInfoFromChromeStorage for async access)');
          }
        } catch (e) { }

        // Method 8: Check ALL localStorage keys for user-related data (more aggressive)
        try {
          var allKeys = Object.keys(localStorage);
          for (var ak = 0; ak < allKeys.length; ak++) {
            try {
              var allValue = localStorage.getItem(allKeys[ak]);
              if (allValue && allValue.length > 10) {
                var allParsed = tryDecodeJson(allValue);
                if (allParsed && typeof allParsed === 'object') {
                  // Deep search for user_id, status, usage_left
                  function deepSearch(obj, target) {
                    if (!obj || typeof obj !== 'object') return null;
                    for (var key in obj) {
                      if (obj.hasOwnProperty(key)) {
                        var lowerKey = key.toLowerCase();
                        if (lowerKey === target || lowerKey.indexOf(target) !== -1) {
                          return obj[key];
                        }
                        if (typeof obj[key] === 'object') {
                          var found = deepSearch(obj[key], target);
                          if (found !== null) return found;
                        }
                      }
                    }
                    return null;
                  }

                  // Search for user_id
                  if (!userInfo.user_id) {
                    var foundId = deepSearch(allParsed, 'user_id') ||
                      deepSearch(allParsed, 'userid') ||
                      deepSearch(allParsed, 'id');
                    if (foundId) {
                      userInfo.userId = foundId;
                      userInfo.user_id = foundId;
                    }
                  }

                  // Search for status
                  if (!userInfo.status) {
                    var foundStatus = deepSearch(allParsed, 'status') ||
                      deepSearch(allParsed, 'accountstatus');
                    if (foundStatus) {
                      userInfo.status = foundStatus;
                    }
                  }

                  // Search for usage_left
                  if (userInfo.usage_left === null) {
                    var foundUsage = deepSearch(allParsed, 'usage_left') ||
                      deepSearch(allParsed, 'usageleft') ||
                      deepSearch(allParsed, 'remaining') ||
                      deepSearch(allParsed, 'remainingusage') ||
                      deepSearch(allParsed, 'usagelimit');
                    if (foundUsage !== null && foundUsage !== undefined) {
                      userInfo.usage_left = foundUsage;
                    }
                  }
                }
              }
            } catch (e) { }
          }
        } catch (e) { }

      } catch (e) {
        Logger.error('Error extracting user info:', e);
      }

      // Clean up and structure output - ALWAYS include user_id, status, usage_left even if null
      var cleaned = {};
      var requiredFields = ['user_id', 'status', 'usage_left'];

      // Always include required fields
      requiredFields.forEach(function (field) {
        if (userInfo[field] !== null && userInfo[field] !== undefined) {
          cleaned[field] = userInfo[field];
        } else {
          // Include as null so user knows we tried
          cleaned[field] = null;
        }
      });

      // Include other fields if they have values
      Object.keys(userInfo).forEach(function (key) {
        if (requiredFields.indexOf(key) === -1 && userInfo[key] !== null && userInfo[key] !== undefined) {
          cleaned[key] = userInfo[key];
        }
      });
      delete cleaned.authToken;
      delete cleaned.accessToken;
      delete cleaned.accessTokenExpiresAt;

      // Log warning if user_id is still null
      if (!cleaned.user_id) {
        Logger.warn('[ChatGPT Extractor] ⚠️ Warning: extractUserInfo could not find user_id. All extraction methods failed.');
      }

      return cleaned;
    },

    /**
     * Get the complete session data as JSON (with uncompressed messages and user info)
     * SYNCHRONOUS VERSION - doesn't include Chrome storage (use exportSessionAsync for that)
     */
    exportSession: function () {
      var userInfo = this.extractUserInfo();

      return {
        sessionId: this.sessionId,
        sessionStartedAt: this.sessionStartedAt,
        exportedAt: Date.now(),
        platform: CONFIG.PLATFORM,
        extractorVersion: CONFIG.VERSION,

        // User information
        user: userInfo,

        // Statistics
        stats: {
          totalChatsVisited: this.stats.totalChatsVisited,
          totalMessagesCollected: this.stats.totalMessagesCollected,
          totalUpdates: this.stats.totalUpdates,
          sessionDuration: Date.now() - this.sessionStartedAt
        },

        // All conversations (in visit order) - with uncompressed messages
        conversations: this.getAllConversations(),

        // Sidebar snapshot
        sidebar: this.sidebarSnapshot
      };
    },

    /**
     * Export session with Chrome storage data (async version)
     * Merges Velocity extension Chrome storage data (userId, usage_left) with page data
     */
    exportSessionAsync: function (callback) {
      var self = this;

      // Get ONLY Chrome storage data (Velocity extension) - skip ChatGPT page extraction
      this.extractUserInfoFromChromeStorage(function (chromeData) {
        // Build clean user info object - remove nulls and duplicates
        var userInfo = {};

        if (chromeData) {
          // User identification (keep only user_id, remove userId duplicate)
          if (chromeData.user_id || chromeData.userId) {
            userInfo.user_id = chromeData.user_id || chromeData.userId;
          }

          // User details (only add if not null)
          if (chromeData.email) {
            userInfo.email = chromeData.email;
          }
          if (chromeData.name) {
            userInfo.name = chromeData.name;
          }

          // Status and usage (keep only usage_left, remove remainingUsage duplicate)
          if (chromeData.usage_left !== null && chromeData.usage_left !== undefined) {
            userInfo.usage_left = chromeData.usage_left;
          } else if (chromeData.remainingUsage !== null && chromeData.remainingUsage !== undefined) {
            userInfo.usage_left = chromeData.remainingUsage;
          }
          // Status (only if not null)
          if (chromeData.status) {
            userInfo.status = chromeData.status;
          }

          // Additional user status data if available
          if (chromeData.userStatus) {
            userInfo.userStatus = chromeData.userStatus;
          }
        }

        var result = {
          sessionId: self.sessionId,
          sessionStartedAt: self.sessionStartedAt,
          exportedAt: Date.now(),
          platform: CONFIG.PLATFORM,
          extractorVersion: CONFIG.VERSION,

          // User information (cleaned - no nulls, no duplicates)
          user: userInfo,

          // Statistics
          stats: {
            totalChatsVisited: self.stats.totalChatsVisited,
            totalMessagesCollected: self.stats.totalMessagesCollected,
            totalUpdates: self.stats.totalUpdates,
            sessionDuration: Date.now() - self.sessionStartedAt
          },

          // All conversations (in visit order) - with uncompressed messages
          conversations: self.getAllConversations(),

          // Sidebar snapshot
          sidebar: self.sidebarSnapshot
        };

        if (callback) callback(result);
      });
    },

    /**
     * Get session summary (without full message content)
     */
    getSummary: function () {
      var conversations = this.getAllConversations();
      return {
        sessionId: this.sessionId,
        sessionDuration: Math.round((Date.now() - this.sessionStartedAt) / 1000) + 's',
        totalChats: conversations.length,
        totalMessages: this.stats.totalMessagesCollected,
        chats: conversations.map(function (c) {
          return {
            chatId: c.chatId,
            title: c.title,
            messageCount: c.messageCount,
            visitCount: c.visitCount,
            lastUpdated: new Date(c.lastUpdated).toLocaleTimeString()
          };
        })
      };
    },

    /**
     * Clear session data (keeps session ID)
     */
    clear: function () {
      this.conversations = {};
      this.visitOrder = [];
      this.sidebarSnapshot = null;
      this.stats = {
        totalChatsVisited: 0,
        totalMessagesCollected: 0,
        totalUpdates: 0
      };

      // Clear from localStorage too
      this.saveToStorage();

      Logger.info('Session store cleared');
    },

    /**
     * Completely reset session (new session ID)
     */
    reset: function () {
      // Clear localStorage
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch (err) {
        Logger.error('Failed to clear localStorage:', err);
      }

      // Re-initialize with fresh session
      this.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
      this.sessionStartedAt = Date.now();
      this.conversations = {};
      this.visitOrder = [];
      this.sidebarSnapshot = null;
      this.stats = {
        totalChatsVisited: 0,
        totalMessagesCollected: 0,
        totalUpdates: 0
      };

      this.saveToStorage();
      Logger.success('🆕 Session reset. New session: ' + this.sessionId);
    },

    /**
     * Force sync from localStorage (useful if out of sync)
     */
    forceSync: function () {
      var stored = this.loadFromStorage();
      if (stored) {
        this.mergeFromOtherTab(stored);
        Logger.success('Force sync completed');
      }
    },

    /**
     * Get sync status
     */
    getSyncStatus: function () {
      return {
        tabId: this.tabId,
        sessionId: this.sessionId,
        localChats: this.visitOrder.length,
        localMessages: this.stats.totalMessagesCollected,
        storageKey: STORAGE_KEY,
        crossTabEnabled: true
      };
    },

    /**
     * Fix chats with missing messages by re-extracting
     * Navigate to each chat and extract messages
     */
    fixMissingMessages: function () {
      var self = this;
      var fixed = 0;
      var needsNavigation = [];
      var failed = 0;

      Logger.info('🔧 Checking for chats with missing messages...');

      Object.keys(this.conversations).forEach(function (chatId) {
        var chat = self.conversations[chatId];

        // Check if chat has messageCount but no messages (or empty messagesCompressed)
        var hasEmptyMessages = (!chat.messages || chat.messages.length === 0);
        var hasEmptyCompressed = (chat.messagesCompressed === '[]' || chat.messagesCompressed === '');

        if (chat.messageCount > 0 && (hasEmptyMessages || hasEmptyCompressed)) {
          // Get current chat ID directly from URL (don't rely on DataCache)
          var currentUrl = window.location.href;
          var currentChatId = DataCache.getChatIdFromUrl(currentUrl);

          Logger.log('   Checking: ' + chat.title);
          Logger.log('      Expected chatId: ' + chatId);
          Logger.log('      Current URL chatId: ' + (currentChatId || 'none'));
          Logger.log('      Current URL: ' + currentUrl);

          // Check if we're on this chat (by ID or by URL match)
          var isOnThisChat = (currentChatId === chatId) || currentUrl.indexOf(chatId) !== -1;

          if (isOnThisChat) {
            // We're on this chat - extract now with retry
            Logger.log('   ✅ On this chat! Extracting messages for: ' + chat.title);

            var extracted = null;
            var retries = 0;
            var maxRetries = 3;

            // Retry extraction up to 3 times
            function tryExtract() {
              Logger.log('   Attempt ' + (retries + 1) + ': Extracting...');
              extracted = extractConversation();

              Logger.log('   Extraction result: success=' + extracted.success + ', messageCount=' + (extracted.messageCount || 0));

              if (extracted.success && extracted.messages && extracted.messages.length > 0) {
                chat.messages = extracted.messages;
                chat.messageCount = extracted.messages.length;

                // Re-compress and save
                var messagesJson = JSON.stringify(chat.messages);
                var compressed = CONFIG.COMPRESS_STORAGE && messagesJson.length > 100 ?
                  Compression.compress(messagesJson) : messagesJson;
                chat.messagesCompressed = compressed;
                chat.contentHash = Compression.generateHash(messagesJson);
                chat.isCompressed = CONFIG.COMPRESS_STORAGE && messagesJson.length > 100;

                self.saveToStorage();
                fixed++;
                Logger.success('✅ Fixed: ' + chat.title + ' (' + extracted.messages.length + ' msgs)');
              } else if (retries < maxRetries) {
                retries++;
                if (extracted.error) {
                  Logger.warn('   Error: ' + extracted.error);
                }
                Logger.log('   Retry ' + retries + '/' + maxRetries + ' in 2 seconds...');
                setTimeout(tryExtract, 2000); // Increased to 2 seconds
              } else {
                failed++;
                Logger.error('❌ Failed to extract messages for: ' + chat.title);
                if (extracted.error) {
                  Logger.error('   Error: ' + extracted.error);
                }
                Logger.warn('   Expected: ' + chat.messageCount + ' messages, got: ' + (extracted.messageCount || 0));
              }
            }

            tryExtract();
          } else {
            needsNavigation.push({ chatId: chatId, title: chat.title, url: chat.url });
          }
        }
      });

      if (needsNavigation.length > 0) {
        Logger.warn('⚠️ ' + needsNavigation.length + ' chat(s) need navigation to fix:');
        needsNavigation.forEach(function(item, index) {
        });
      }

      if (fixed > 0) {
        Logger.success('✅ Fixed ' + fixed + ' chat(s)');
      }
      if (failed > 0) {
        Logger.warn('❌ Failed to fix ' + failed + ' chat(s)');
      }

      return {
        fixed: fixed,
        needsNavigation: needsNavigation.length,
        failed: failed,
        needsNavigationList: needsNavigation
      };
    },

    /**
     * Force fix current chat (extract and save messages for chat you're currently on)
     */
    fixCurrentChat: function () {
      var currentChatId = DataCache.getChatIdFromUrl();
      var currentUrl = window.location.href;

      if (!currentChatId) {
        Logger.warn('⚠️ Not on a conversation page. Navigate to a chat first.');
        return { success: false, error: 'Not on a conversation page' };
      }

      Logger.info('🔧 Fixing current chat: ' + currentChatId);
      Logger.log('   URL: ' + currentUrl);

      // Extract messages
      var extracted = extractConversation();

      if (!extracted.success) {
        Logger.error('❌ Extraction failed: ' + (extracted.error || 'Unknown error'));
        return { success: false, error: extracted.error };
      }

      if (!extracted.messages || extracted.messages.length === 0) {
        Logger.warn('⚠️ No messages found. The chat might be empty or page not fully loaded.');
        Logger.warn('   Try waiting a few seconds and run again.');
        return { success: false, error: 'No messages found', extracted: extracted };
      }

      // Find or create chat entry
      var chat = this.conversations[currentChatId];
      if (!chat) {
        // Create new entry
        chat = {
          chatId: currentChatId,
          title: this.extractTitle(currentChatId, extracted),
          url: currentUrl,
          firstVisited: Date.now(),
          lastUpdated: Date.now(),
          visitCount: 1,
          messageCount: extracted.messageCount,
          messages: extracted.messages,
          richContentSummary: extracted.richContentSummary
        };
        this.conversations[currentChatId] = chat;
        if (this.visitOrder.indexOf(currentChatId) === -1) {
          this.visitOrder.push(currentChatId);
        }
        this.stats.totalChatsVisited++;
      } else {
        // Update existing
        chat.messages = extracted.messages;
        chat.messageCount = extracted.messageCount;
        chat.lastUpdated = Date.now();
        chat.visitCount++;
        chat.richContentSummary = extracted.richContentSummary || chat.richContentSummary;
      }

      // Compress and save
      var messagesJson = JSON.stringify(chat.messages);
      var compressed = CONFIG.COMPRESS_STORAGE && messagesJson.length > 100 ?
        Compression.compress(messagesJson) : messagesJson;
      chat.messagesCompressed = compressed;
      chat.contentHash = Compression.generateHash(messagesJson);
      chat.isCompressed = CONFIG.COMPRESS_STORAGE && messagesJson.length > 100;

      this.saveToStorage();

      Logger.success('✅ Fixed current chat: ' + chat.title);
      Logger.log('   Messages: ' + chat.messageCount);
      Logger.log('   Saved and compressed');

      return {
        success: true,
        chatId: currentChatId,
        title: chat.title,
        messageCount: chat.messageCount
      };
    },

    /**
     * List all chats with missing messages (for manual fixing)
     */
    listMissingMessages: function () {
      var self = this;
      var missing = [];

      Object.keys(this.conversations).forEach(function (chatId) {
        var chat = self.conversations[chatId];
        var hasEmptyMessages = (!chat.messages || chat.messages.length === 0);
        var hasEmptyCompressed = (chat.messagesCompressed === '[]' || chat.messagesCompressed === '');

        if (chat.messageCount > 0 && (hasEmptyMessages || hasEmptyCompressed)) {
          missing.push({
            chatId: chatId,
            title: chat.title,
            url: chat.url,
            messageCount: chat.messageCount,
            hasMessages: chat.messages && chat.messages.length > 0
          });
        }
      });

      if (missing.length > 0) {
        Logger.warn('⚠️ Found ' + missing.length + ' chat(s) with missing messages:');
        missing.forEach(function (item, index) {
        });
        Logger.warn('   💡 To fix: Navigate to each URL above, then run:');
        Logger.warn('      VelocityDemo.fixMissing()');
      } else {
        Logger.success('✅ All chats have messages!');
      }

      return missing;
    },

    /**
     * Debug function - show current state
     */
    debug: function () {
      var self = this;
      Object.keys(this.conversations).forEach(function(chatId) {
        var chat = self.conversations[chatId];
      });

      // Check localStorage
      try {
        var stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          var parsed = JSON.parse(stored);
        } else {
        }
      } catch (e) {
      }

      return {
        sessionId: this.sessionId,
        memoryChats: Object.keys(this.conversations),
        visitOrder: this.visitOrder,
        stats: this.stats
      };
    }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // LOGGING UTILITIES
  // ═══════════════════════════════════════════════════════════════════════════

  // Quiet by default in Sidebar_extension to avoid hammering the host page's
  // main thread. Enable verbose logs by running this in the AI tab console:
  //   localStorage.setItem('velocity_sidebar_debug', '1'); location.reload();
  function __velocityQuiet() {
    try {
      if (typeof window !== 'undefined' && window.__VELOCITY_EXTRACTOR_DEBUG__) return false;
      if (typeof localStorage !== 'undefined' && localStorage.getItem('velocity_sidebar_debug') === '1') return false;
    } catch (e) { /* ignore */ }
    return true;
  }

  var Logger = {
    prefix: '[ChatGPT Extractor]',

    // Verbose logs (silenced in quiet mode)
    log: function () {
      if (__velocityQuiet()) return;
      var args = Array.prototype.slice.call(arguments);
      args.unshift(this.prefix);
      console.log.apply(console, args);
    },
    // Info (silenced in quiet mode)
    info: function () {
      if (__velocityQuiet()) return;
      var args = Array.prototype.slice.call(arguments);
      args.unshift(this.prefix + ' ℹ️');
      console.info.apply(console, args);
    },
    // Warnings (silenced in quiet mode)
    warn: function () {
      if (__velocityQuiet()) return;
      var args = Array.prototype.slice.call(arguments);
      args.unshift(this.prefix + ' ⚠️');
      console.warn.apply(console, args);
    },
    // Errors - always shown (critical)
    error: function () {
      var args = Array.prototype.slice.call(arguments);
      args.unshift(this.prefix + ' ❌');
      console.error.apply(console, args);
    },
    // Success
    success: function () {
      var args = Array.prototype.slice.call(arguments);
      var message = args[0] || '';
      if (CONFIG.VERBOSE || 
          message.indexOf('Saved') !== -1 || 
          message.indexOf('messages') !== -1 && (message.indexOf('Saved') !== -1 || message.indexOf('NEW') !== -1) ||
          message.indexOf('session') !== -1 && message.indexOf('started') !== -1) {
        args.unshift(this.prefix + ' ✅');
        console.log.apply(console, args);
      }
    },
    // Debug
    debug: function () {
      var args = Array.prototype.slice.call(arguments);
      args.unshift(this.prefix + ' 🔍');
      console.debug.apply(console, args);
    },
    // JSON output - shows formatted JSON in console (helpful for extraction)
    json: function (data, label) {
      label = label || 'Extracted Data';  
    },
    group: function (label) {
    },
    groupEnd: function () {
    },
    table: function (data) {
    }
  };

  // Initialize SessionStore after Logger is available
  SessionStore.init();

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 1: CONVERSATION ROOT DETECTION
  // ═══════════════════════════════════════════════════════════════════════════

  function findConversationRoot() {
    // Verbose: Root finding details
    if (CONFIG.VERBOSE) {
      Logger.group('🎯 Finding Conversation Root');
    }

    var mainElement = document.querySelector('main');
    if (mainElement) {
      if (CONFIG.VERBOSE) {
        Logger.success('Found <main> element as root');
        Logger.groupEnd();
      }
      return mainElement;
    }

    var roleMain = document.querySelector('[role="main"]');
    if (roleMain) {
      if (CONFIG.VERBOSE) {
        Logger.success('Found [role="main"] element as root');
        Logger.groupEnd();
      }
      return roleMain;
    }

    var conversationSelectors = [
      '[data-testid*="conversation"]',
      '[class*="conversation"]',
      '[class*="chat-messages"]',
      '[class*="thread"]',
      '[data-testid*="chat-messages"]',
      '[class*="chat-container"]',
      '[data-testid*="conversation-container"]',
      '#__next main',
      '.chat-container',
      '[role="main"] .flex'
    ];

    for (var i = 0; i < conversationSelectors.length; i++) {
      try {
        var element = document.querySelector(conversationSelectors[i]);
        if (element && element.offsetHeight > 100) {
          if (CONFIG.VERBOSE) {
            Logger.success('Found conversation container via: ' + conversationSelectors[i]);
            Logger.groupEnd();
          }
          return element;
        }
      } catch (e) { }
    }

    Logger.warn('Using document.body as fallback root');
    if (CONFIG.VERBOSE) {
      Logger.groupEnd();
    }
    return document.body;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 2: MESSAGE CANDIDATE COLLECTION
  // ═══════════════════════════════════════════════════════════════════════════

  function collectMessageCandidates(root) {
    Logger.group('🔎 Collecting Message Candidates');

    var candidates = [];
    var seen = new Set();

    function addCandidate(el) {
      if (!seen.has(el)) {
        seen.add(el);
        candidates.push(el);
      }
    }

    // Strategy 1: Elements with data-message-author-role (Best case)
    var dataMessageElements = root.querySelectorAll('[data-message-author-role]');
    dataMessageElements.forEach(addCandidate);
    Logger.log('Strategy 1 (data-message-author-role): ' + dataMessageElements.length + ' elements');

    // Strategy 2: Elements with message-related data attributes (updated for current ChatGPT)
    var messageDataAttrs = root.querySelectorAll('[data-message-id], [data-testid*="message"], [data-testid*="conversation-turn"], [data-testid*="turn"]');
    messageDataAttrs.forEach(addCandidate);
    Logger.log('Strategy 2 (data-message-id): ' + messageDataAttrs.length + ' elements');

    // Strategy 3: Article elements and conversation items
    var articles = root.querySelectorAll('article, [data-testid*="conversation-item"], [class*="conversation-turn"], [class*="message-wrapper"]');
    articles.forEach(addCandidate);
    Logger.log('Strategy 3 (article/conversation-item): ' + articles.length + ' elements');

    // Strategy 4: Turn-based containers (updated for current ChatGPT)
    var turnContainers = root.querySelectorAll('[data-testid*="turn"], [class*="turn"], [data-testid*="conversation-turn"], [class*="message-turn"]');
    turnContainers.forEach(addCandidate);
    Logger.log('Strategy 4 (turn containers): ' + turnContainers.length + ' elements');

    // Strategy 5: Role-based containers and message containers
    var roleContainers = root.querySelectorAll('[data-role], [role="article"], [role="row"], [data-testid*="message"], [class*="message"]');
    roleContainers.forEach(addCandidate);
    Logger.log('Strategy 5 (role containers): ' + roleContainers.length + ' elements');

    // Strategy 5.5: ChatGPT specific containers (added for current UI)
    var chatGptContainers = root.querySelectorAll('[class*="agent-turn"], [class*="user-turn"], [data-testid*="chat-message"], [class*="chat-message"]');
    chatGptContainers.forEach(addCandidate);
    Logger.log('Strategy 5.5 (ChatGPT containers): ' + chatGptContainers.length + ' elements');

    // Strategy 6: Scroll container children
    var scrollContainers = root.querySelectorAll('[style*="overflow"], [class*="scroll"]');
    scrollContainers.forEach(function (container) {
      var directChildren = container.children;
      if (directChildren.length > 2) {
        Array.from(directChildren).forEach(function (child) {
          if (child.innerText && child.innerText.trim().length > CONFIG.MIN_TEXT_LENGTH) {
            addCandidate(child);
          }
        });
      }
    });
    Logger.log('Strategy 6 (scroll containers): checked ' + scrollContainers.length + ' containers');

    Logger.success('Total unique candidates: ' + candidates.length);
    Logger.groupEnd();

    return candidates;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 3: MESSAGE FILTERING
  // ═══════════════════════════════════════════════════════════════════════════

  function isElementVisible(element) {
    if (!element) return false;
    if (!document.body.contains(element)) return false;

    var rect = element.getBoundingClientRect();
    if (rect.height < CONFIG.MIN_VISIBLE_HEIGHT) return false;

    var style = window.getComputedStyle(element);
    if (style.display === 'none') return false;
    if (style.visibility === 'hidden') return false;
    if (parseFloat(style.opacity) === 0) return false;

    return true;
  }

  function isNoiseElement(element) {
    var tagName = element.tagName.toLowerCase();
    var noiseTags = ['nav', 'header', 'footer', 'aside', 'form', 'input', 'textarea', 'button'];
    if (noiseTags.indexOf(tagName) !== -1) return true;

    var role = element.getAttribute('role');
    var noiseRoles = ['navigation', 'banner', 'contentinfo', 'complementary', 'form'];
    if (role && noiseRoles.indexOf(role) !== -1) return true;

    // Check ID for Velocity extension elements
    var idAttr = element.id || '';
    var noiseIds = ['velocity', 'popupbox', 'popup-box', 'velocitypopup', 'velocity-popup', 'velocity-button', 'velocitybutton'];
    if (idAttr) {
      var lowerId = idAttr.toLowerCase();
      for (var j = 0; j < noiseIds.length; j++) {
        if (lowerId.indexOf(noiseIds[j]) !== -1) return true;
      }
    }

    var classAttr = element.className || '';
    var noisePatterns = [
      'sidebar', 'nav', 'menu', 'header', 'footer', 'modal', 'popup', 'tooltip', 'input', 'composer',
      // Velocity extension patterns
      'velocity', 'popupbox', 'popup-box', 'velocitypopup', 'velocity-popup',
      'velocity-button', 'velocitybutton', 'velocity-container', 'velocity-overlay',
      'velocity-modal', 'velocity-input', 'velocity-wrapper'
    ];
    if (typeof classAttr === 'string') {
      var lowerClass = classAttr.toLowerCase();
      for (var i = 0; i < noisePatterns.length; i++) {
        if (lowerClass.indexOf(noisePatterns[i]) !== -1) return true;
      }
    }

    // Check if element is inside a Velocity container
    var parent = element.parentElement;
    var depth = 0;
    while (parent && depth < 10) {
      var parentId = (parent.id || '').toLowerCase();
      var parentClass = (parent.className || '').toLowerCase();
      if (parentId.indexOf('velocity') !== -1 || parentClass.indexOf('velocity') !== -1 ||
        parentId.indexOf('popupbox') !== -1 || parentClass.indexOf('popupbox') !== -1) {
        return true;
      }
      parent = parent.parentElement;
      depth++;
    }

    return false;
  }

  /**
   * Check if text content is JavaScript code/analytics (noise)
   */
  function isJavaScriptNoise(text) {
    if (!text || typeof text !== 'string') return false;

    var lowerText = text.toLowerCase();

    // Patterns that indicate JavaScript code/analytics
    var jsPatterns = [
      'window.__oai_',           // ChatGPT analytics
      'window.__oai_log',        // ChatGPT logging
      'requestanimationframe',   // Browser API
      'date.now()',              // Common in analytics
      'console.log',             // Console logging
      'window.location',         // Location access
      'document.cookie',         // Cookie access
      'localstorage',            // Storage access
      'sessionstorage',          // Storage access
      'addEventListener',        // Event listeners
      'removeEventListener',     // Event listeners
      'settimeout',              // Timers
      'setinterval',             // Timers
      'function()',              // Anonymous functions
      '=>',                      // Arrow functions
      'typeof',                  // Type checking
      'instanceof',              // Type checking
      'new date',                // Date creation
      'json.parse',              // JSON parsing
      'json.stringify',          // JSON stringify
      'object.keys',             // Object methods
      'array.prototype',         // Array methods
      'window.',                 // Window object access (if very short)
      'document.',               // Document object access (if very short)
      'navigator.',              // Navigator object
      'performance.',            // Performance API
      'webpack',                 // Build tool references
      '__webpack_require__',     // Webpack internals
      'eval(',                   // Eval calls
      'new function',            // Function constructor
    ];

    // Check for JavaScript patterns
    for (var i = 0; i < jsPatterns.length; i++) {
      if (lowerText.indexOf(jsPatterns[i]) !== -1) {
        // Additional check: if it's mostly code-like (has multiple JS patterns or is very code-heavy)
        var patternCount = 0;
        for (var j = 0; j < jsPatterns.length; j++) {
          if (lowerText.indexOf(jsPatterns[j]) !== -1) patternCount++;
        }

        // If it has multiple JS patterns OR is very short and contains JS, it's likely noise
        if (patternCount >= 2 || (text.length < 200 && patternCount >= 1)) {
          return true;
        }
      }
    }

    // Check for code-like structure (lots of parentheses, brackets, semicolons)
    var codeChars = (text.match(/[{}();=]/g) || []).length;
    var totalChars = text.length;
    if (totalChars > 0 && codeChars / totalChars > 0.3 && text.length < 500) {
      // More than 30% code characters and relatively short = likely code
      return true;
    }

    return false;
  }

  function extractTextContent(element) {
    if (!element) return '';

    var text = element.innerText || element.textContent || '';
    text = text
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/[ \t]+/g, ' ')
      .replace(/^ +/gm, '')
      .replace(/ +$/gm, '')
      .trim();

    return text;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RICH CONTENT EXTRACTION
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Extracts code blocks from an element
   * @param {HTMLElement} element - Message element
   * @returns {Array} Array of code block objects
   */
  function extractCodeBlocks(element) {
    if (!element) return [];

    var codeBlocks = [];
    var codeElements = element.querySelectorAll('pre code, pre, [class*="code-block"], [class*="hljs"]');
    var seenCode = new Set();

    codeElements.forEach(function (codeEl, index) {
      // Get the actual code content
      var code = codeEl.textContent || codeEl.innerText || '';
      code = code.trim();

      // Skip empty or duplicate code
      if (!code || code.length < 3) return;
      var codeSignature = code.substring(0, 100);
      if (seenCode.has(codeSignature)) return;
      seenCode.add(codeSignature);

      // Detect language from class
      var language = 'text';
      var classes = (codeEl.className || '') + ' ' + ((codeEl.parentElement && codeEl.parentElement.className) || '');

      // Common language patterns
      var langPatterns = [
        /language-(\w+)/i,
        /lang-(\w+)/i,
        /hljs-?(\w+)/i,
        /\b(python|javascript|typescript|java|cpp|c\+\+|csharp|c#|ruby|go|rust|php|swift|kotlin|scala|sql|html|css|json|xml|yaml|bash|shell|powershell|markdown|plaintext)\b/i
      ];

      for (var i = 0; i < langPatterns.length; i++) {
        var match = classes.match(langPatterns[i]);
        if (match) {
          language = match[1].toLowerCase();
          break;
        }
      }

      // Normalize language names
      var langMap = {
        'js': 'javascript',
        'ts': 'typescript',
        'py': 'python',
        'rb': 'ruby',
        'cs': 'csharp',
        'c++': 'cpp',
        'c#': 'csharp',
        'sh': 'bash',
        'zsh': 'bash',
        'yml': 'yaml'
      };
      language = langMap[language] || language;

      codeBlocks.push({
        id: 'code_' + (codeBlocks.length + 1),
        language: language,
        code: code,
        lineCount: code.split('\n').length,
        charCount: code.length,
        position: index + 1
      });
    });

    return codeBlocks;
  }

  /**
   * Extracts images from an element
   * @param {HTMLElement} element - Message element
   * @returns {Array} Array of image objects
   */
  function extractImages(element) {
    if (!element) return [];

    var images = [];
    var imgElements = element.querySelectorAll('img');
    var seenUrls = new Set();

    imgElements.forEach(function (img, index) {
      var src = img.src || img.getAttribute('src') || '';

      // Skip tiny images (icons), duplicates, or empty src
      if (!src || seenUrls.has(src)) return;
      if (img.width < 50 && img.height < 50) return;

      seenUrls.add(src);

      var alt = img.alt || img.getAttribute('alt') || '';
      var title = img.title || img.getAttribute('title') || '';

      // Determine image type
      var imageType = 'image';
      if (src.indexOf('blob:') === 0) {
        imageType = 'uploaded';
      } else if (src.indexOf('oaiusercontent') !== -1 || src.indexOf('dalle') !== -1) {
        imageType = 'generated';
      }

      images.push({
        id: 'img_' + (images.length + 1),
        type: imageType,
        src: src,
        alt: alt,
        title: title,
        width: img.naturalWidth || img.width || null,
        height: img.naturalHeight || img.height || null,
        placeholder: '[Image' + (alt ? ': ' + alt : '') + ']'
      });
    });

    return images;
  }

  /**
   * Extracts file attachments from an element
   * @param {HTMLElement} element - Message element
   * @returns {Array} Array of file objects
   */
  function extractFiles(element) {
    if (!element) return [];

    var files = [];

    // Look for file attachment indicators
    var fileSelectors = [
      '[class*="attachment"]',
      '[class*="file-"]',
      '[data-testid*="file"]',
      '[class*="upload"]',
      'a[download]',
      '[class*="document"]'
    ];

    var fileElements = element.querySelectorAll(fileSelectors.join(', '));
    var seenFiles = new Set();

    fileElements.forEach(function (fileEl, index) {
      // Try to extract filename
      var filename = '';
      var filenameEl = fileEl.querySelector('[class*="filename"], [class*="name"], span, p');
      if (filenameEl) {
        filename = filenameEl.textContent.trim();
      } else {
        filename = fileEl.textContent.trim();
      }

      // Skip if no valid filename or already seen
      if (!filename || filename.length < 2 || seenFiles.has(filename)) return;
      seenFiles.add(filename);

      // Detect file type from extension
      var ext = '';
      var extMatch = filename.match(/\.(\w+)$/);
      if (extMatch) {
        ext = extMatch[1].toLowerCase();
      }

      // Map extension to mime type
      var mimeTypes = {
        'pdf': 'application/pdf',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xls': 'application/vnd.ms-excel',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'ppt': 'application/vnd.ms-powerpoint',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'txt': 'text/plain',
        'csv': 'text/csv',
        'json': 'application/json',
        'xml': 'application/xml',
        'zip': 'application/zip',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'mp3': 'audio/mpeg',
        'mp4': 'video/mp4'
      };

      files.push({
        id: 'file_' + (files.length + 1),
        name: filename,
        extension: ext,
        mimeType: mimeTypes[ext] || 'application/octet-stream',
        placeholder: '[File: ' + filename + ']'
      });
    });

    return files;
  }

  /**
   * Extracts tables from an element
   * @param {HTMLElement} element - Message element
   * @returns {Array} Array of table objects
   */
  function extractTables(element) {
    if (!element) return [];

    var tables = [];
    var tableElements = element.querySelectorAll('table');

    tableElements.forEach(function (table, index) {
      var headers = [];
      var rows = [];

      // Extract headers
      var headerCells = table.querySelectorAll('thead th, thead td, tr:first-child th');
      headerCells.forEach(function (th) {
        headers.push(th.textContent.trim());
      });

      // Extract rows
      var rowElements = table.querySelectorAll('tbody tr, tr');
      rowElements.forEach(function (tr, rowIndex) {
        // Skip header row if already extracted
        if (rowIndex === 0 && headers.length > 0 && tr.querySelector('th')) return;

        var rowData = [];
        var cells = tr.querySelectorAll('td, th');
        cells.forEach(function (cell) {
          rowData.push(cell.textContent.trim());
        });

        if (rowData.length > 0) {
          rows.push(rowData);
        }
      });

      if (headers.length > 0 || rows.length > 0) {
        tables.push({
          id: 'table_' + (tables.length + 1),
          headers: headers,
          rows: rows,
          rowCount: rows.length,
          columnCount: headers.length || (rows[0] ? rows[0].length : 0),
          position: index + 1
        });
      }
    });

    return tables;
  }

  /**
   * Extracts math/LaTeX formulas from an element
   * @param {HTMLElement} element - Message element
   * @returns {Array} Array of formula objects
   */
  function extractFormulas(element) {
    if (!element) return [];

    var formulas = [];
    var formulaSelectors = [
      '.katex',
      '.MathJax',
      '[class*="math"]',
      'math',
      '[data-formula]'
    ];

    var formulaElements = element.querySelectorAll(formulaSelectors.join(', '));
    var seenFormulas = new Set();

    formulaElements.forEach(function (formulaEl, index) {
      // Try to get LaTeX source
      var latex = '';
      var annotation = formulaEl.querySelector('annotation[encoding*="tex"], annotation');
      if (annotation) {
        latex = annotation.textContent.trim();
      } else {
        latex = formulaEl.getAttribute('data-formula') ||
          formulaEl.getAttribute('data-latex') ||
          formulaEl.getAttribute('title') || '';
      }

      // Get rendered text
      var rendered = formulaEl.textContent.trim();

      // Skip empty or duplicate
      if ((!latex && !rendered) || seenFormulas.has(latex + rendered)) return;
      seenFormulas.add(latex + rendered);

      // Determine if block or inline
      var isBlock = formulaEl.classList.contains('katex-display') ||
        formulaEl.classList.contains('MathJax_Display') ||
        formulaEl.tagName === 'MATH' && formulaEl.getAttribute('display') === 'block';

      formulas.push({
        id: 'formula_' + (formulas.length + 1),
        latex: latex,
        rendered: rendered,
        type: isBlock ? 'block' : 'inline',
        position: index + 1
      });
    });

    return formulas;
  }

  /**
   * Extracts artifacts/canvas from the page (ChatGPT specific)
   * @param {HTMLElement} element - Message element
   * @returns {Array} Array of artifact objects
   */
  function extractArtifacts(element) {
    if (!element) return [];

    var artifacts = [];

    // Look for artifact/canvas containers
    var artifactSelectors = [
      '[class*="artifact"]',
      '[class*="canvas"]',
      '[data-testid*="artifact"]',
      '[data-testid*="canvas"]',
      '[class*="code-output"]',
      '[class*="rendered"]'
    ];

    var artifactElements = element.querySelectorAll(artifactSelectors.join(', '));

    artifactElements.forEach(function (artifactEl, index) {
      // Try to determine artifact type
      var type = 'unknown';
      var title = '';
      var content = '';
      var language = null;

      // Check for title
      var titleEl = artifactEl.querySelector('[class*="title"], [class*="header"] span, h1, h2, h3');
      if (titleEl) {
        title = titleEl.textContent.trim();
      }

      // Check for code content
      var codeEl = artifactEl.querySelector('pre code, pre, code');
      if (codeEl) {
        type = 'code';
        content = codeEl.textContent.trim();

        // Try to detect language
        var classes = codeEl.className || '';
        var langMatch = classes.match(/language-(\w+)|lang-(\w+)/i);
        if (langMatch) {
          language = (langMatch[1] || langMatch[2]).toLowerCase();
        }
      } else {
        // Check for other content types
        var textContent = artifactEl.textContent.trim();
        if (textContent.length > 50) {
          type = 'document';
          content = textContent;
        }
      }

      if (type !== 'unknown' && content) {
        artifacts.push({
          id: 'artifact_' + (artifacts.length + 1),
          type: type,
          title: title || 'Untitled',
          language: language,
          content: content,
          charCount: content.length,
          position: index + 1
        });
      }
    });

    return artifacts;
  }

  /**
   * Extracts all rich content from a message element
   * @param {HTMLElement} element - Message element
   * @returns {Object} Rich content object
   */
  function extractRichContent(element) {
    if (!element) {
      return {
        hasRichContent: false,
        codeBlocks: [],
        images: [],
        files: [],
        tables: [],
        formulas: [],
        artifacts: []
      };
    }

    var codeBlocks = extractCodeBlocks(element);
    var images = extractImages(element);
    var files = extractFiles(element);
    var tables = extractTables(element);
    var formulas = extractFormulas(element);
    var artifacts = extractArtifacts(element);

    var hasRichContent = codeBlocks.length > 0 ||
      images.length > 0 ||
      files.length > 0 ||
      tables.length > 0 ||
      formulas.length > 0 ||
      artifacts.length > 0;

    return {
      hasRichContent: hasRichContent,
      codeBlocks: codeBlocks,
      images: images,
      files: files,
      tables: tables,
      formulas: formulas,
      artifacts: artifacts
    };
  }

  function filterRealMessages(candidates) {
    Logger.group('🧹 Filtering Real Messages');

    var realMessages = [];
    var reasons = { notVisible: 0, isNoise: 0, noText: 0, tooShort: 0, duplicate: 0, jsNoise: 0, passed: 0 };
    var seenTexts = new Set();
    var filteredDetails = []; // For debugging

    for (var i = 0; i < candidates.length; i++) {
      var candidate = candidates[i];
      var reason = null;

      // Check visibility (less strict - allow if has any height)
      var rect = candidate.getBoundingClientRect();
      var isVisible = rect.height > 0 && rect.width > 0;
      var style = window.getComputedStyle(candidate);
      var isHidden = style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0;

      if (isHidden) {
        reasons.notVisible++;
        reason = 'hidden';
        continue;
      }

      // Allow even if very small (might be collapsed initially)
      // Only reject if truly zero height
      if (rect.height === 0 && rect.width === 0) {
        reasons.notVisible++;
        reason = 'zero-size';
        continue;
      }

      if (isNoiseElement(candidate)) {
        reasons.isNoise++;
        reason = 'noise';
        continue;
      }

      var text = extractTextContent(candidate);
      if (!text) {
        reasons.noText++;
        reason = 'no-text';
        // Check if it has rich content instead
        var hasCode = candidate.querySelector('pre, code');
        var hasImages = candidate.querySelector('img');
        if (!hasCode && !hasImages) {
          continue;
        }
        // Has rich content, allow it even without text
        text = '[Rich content: ' + (hasCode ? 'code' : '') + (hasImages ? 'image' : '') + ']';
      }

      // Check for JavaScript code/analytics noise
      if (isJavaScriptNoise(text)) {
        reasons.jsNoise++;
        reason = 'js-noise';
        Logger.log('   Filtered JS noise: ' + text.substring(0, 50) + '...');
        continue;
      }

      // Lower minimum text length for rich content
      var hasRichContent = candidate.querySelector('pre, code, img, table');
      var minLength = hasRichContent ? 2 : CONFIG.MIN_TEXT_LENGTH;

      if (text.length < minLength) {
        reasons.tooShort++;
        reason = 'too-short';
        continue;
      }

      var textSignature = text.substring(0, 200);
      if (seenTexts.has(textSignature)) {
        reasons.duplicate++;
        reason = 'duplicate';
        continue;
      }
      seenTexts.add(textSignature);

      realMessages.push(candidate);
      reasons.passed++;
    }

    Logger.log('Filter results:', reasons);

    // If no messages passed, show detailed diagnostics (verbose only — the
    // multi-line warn block produces large DevTools stack traces that
    // themselves degrade host-page responsiveness).
    if (realMessages.length === 0 && candidates.length > 0) {
      if (CONFIG.VERBOSE) {
        Logger.warn('⚠️ All messages filtered out! Diagnostics:');
        Logger.warn('   Total candidates: ' + candidates.length);
        Logger.warn('   Filtered out:');
        Logger.warn('     • Not visible: ' + reasons.notVisible);
        Logger.warn('     • Noise: ' + reasons.isNoise);
        Logger.warn('     • No text: ' + reasons.noText);
        Logger.warn('     • Too short: ' + reasons.tooShort);
        Logger.warn('     • Duplicate: ' + reasons.duplicate);
        Logger.warn('');
        Logger.warn('   💡 Trying fallback: Less strict filtering...');
      }

      // Fallback: Accept any candidate with some content
      var fallbackMessages = [];
      for (var j = 0; j < candidates.length; j++) {
        var cand = candidates[j];
        if (isNoiseElement(cand)) continue; // Still filter noise

        var candText = extractTextContent(cand);
        var hasContent = candText && candText.length >= 2;
        var hasRich = cand.querySelector('pre, code, img, table');

        if (hasContent || hasRich) {
          fallbackMessages.push(cand);
        }
      }

      if (fallbackMessages.length > 0) {
        Logger.success('✅ Fallback found ' + fallbackMessages.length + ' messages');
        Logger.groupEnd();
        return fallbackMessages;
      }
    }

    Logger.success('Filtered to ' + realMessages.length + ' real messages');
    Logger.groupEnd();

    return realMessages;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 4: ROLE DETECTION
  // ═══════════════════════════════════════════════════════════════════════════

  function detectMessageRole(element, index) {
    // PRIMARY: Check data-message-author-role attribute
    var directRole = element.getAttribute('data-message-author-role');
    if (directRole) {
      var normalizedRole = directRole.toLowerCase().trim();
      if (normalizedRole === 'user') return 'user';
      if (normalizedRole === 'assistant' || normalizedRole === 'system') return 'assistant';
    }

    // Check parent elements (up to 5 levels)
    var parent = element.parentElement;
    var depth = 0;
    while (parent && depth < 5) {
      var parentRole = parent.getAttribute('data-message-author-role');
      if (parentRole) {
        var pNormalized = parentRole.toLowerCase().trim();
        if (pNormalized === 'user') return 'user';
        if (pNormalized === 'assistant' || pNormalized === 'system') return 'assistant';
      }
      parent = parent.parentElement;
      depth++;
    }

    // Check child elements
    var childWithRole = element.querySelector('[data-message-author-role]');
    if (childWithRole) {
      var childRole = childWithRole.getAttribute('data-message-author-role');
      if (childRole) {
        var cNormalized = childRole.toLowerCase().trim();
        if (cNormalized === 'user') return 'user';
        if (cNormalized === 'assistant' || cNormalized === 'system') return 'assistant';
      }
    }

    // SECONDARY: Structural indicators
    var hasUserIndicators = element.querySelector('[data-testid*="user"]') ||
      element.querySelector('[class*="user-message"]') ||
      element.querySelector('img[alt*="User"]');
    if (hasUserIndicators) {
      Logger.debug('Role detected via user indicators at index ' + index);
      return 'user';
    }

    var hasAssistantIndicators = element.querySelector('[data-testid*="assistant"]') ||
      element.querySelector('[class*="assistant"]') ||
      element.querySelector('[class*="bot"]') ||
      element.querySelector('img[alt*="ChatGPT"]') ||
      element.querySelector('img[alt*="GPT"]');
    if (hasAssistantIndicators) {
      Logger.debug('Role detected via assistant indicators at index ' + index);
      return 'assistant';
    }

    // TERTIARY: Content heuristics
    var text = extractTextContent(element);
    var hasCodeBlock = element.querySelector('pre, code') !== null;
    var hasList = element.querySelector('ul, ol') !== null;
    var hasHeading = element.querySelector('h1, h2, h3, h4') !== null;
    var hasParagraphs = element.querySelectorAll('p').length > 2;
    var isLong = text.length > 500;
    var hasMarkdown = /```|`[^`]+`|\*\*[^*]+\*\*|#{1,3}\s/.test(text);

    var assistantScore = (hasCodeBlock ? 1 : 0) + (hasList ? 1 : 0) + (hasHeading ? 1 : 0) +
      (hasParagraphs ? 1 : 0) + (isLong ? 1 : 0) + (hasMarkdown ? 1 : 0);

    var isShort = text.length < 300;
    var isPlainText = !hasCodeBlock && !hasList;
    var noFormatting = !hasMarkdown;
    var singleParagraph = element.querySelectorAll('p').length <= 1;
    var endsWithQuestion = /\?$/.test(text.trim());

    var userScore = (isShort ? 1 : 0) + (isPlainText ? 1 : 0) + (noFormatting ? 1 : 0) +
      (singleParagraph ? 1 : 0) + (endsWithQuestion ? 1 : 0);

    Logger.debug('Role heuristics at index ' + index + ': assistantScore=' + assistantScore + ', userScore=' + userScore);

    if (assistantScore >= 3) return 'assistant';
    if (userScore >= 4 && assistantScore < 2) return 'user';

    // FALLBACK: Position-based alternating
    Logger.debug('Using position-based fallback for index ' + index);
    return index % 2 === 0 ? 'user' : 'assistant';
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 5: TIMESTAMP GENERATION
  // ═══════════════════════════════════════════════════════════════════════════

  function generateSyntheticTimestamps(messageCount) {
    Logger.log('Generating ' + messageCount + ' synthetic timestamps');

    if (messageCount === 0) return [];

    var now = Date.now();
    var totalDuration = (messageCount - 1) * CONFIG.TIMESTAMP_INTERVAL_MS;
    var baseTime = now - totalDuration;

    var timestamps = [];
    for (var i = 0; i < messageCount; i++) {
      timestamps.push(baseTime + (i * CONFIG.TIMESTAMP_INTERVAL_MS));
    }

    if (timestamps.length > 0) {
      Logger.debug('Timestamp range: ' + new Date(timestamps[0]).toISOString() + ' to ' + new Date(timestamps[timestamps.length - 1]).toISOString());
    }

    return timestamps;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 6: SESSION ID GENERATION
  // ═══════════════════════════════════════════════════════════════════════════

  function generateSessionId() {
    var timestamp = Math.floor(Date.now() / 1000);
    var random = Math.random().toString(36).substring(2, 8);
    return CONFIG.PLATFORM + '_' + timestamp + '_' + random;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 7: JSON ASSEMBLY
  // ═══════════════════════════════════════════════════════════════════════════

  function assembleConversationPayload(messages) {
    log('[ChatGPT Extractor] 🔧 Assembling JSON payload...');
    var sessionId = generateSessionId();
    var chatId = DataCache.getChatIdFromUrl();

    // Extract user information and inject into payload
    var userInfo = SessionStore.extractUserInfo();

    // Ensure messages is an array
    if (!Array.isArray(messages)) {
      messages = [];
      warn('[ChatGPT Extractor] ⚠️ Messages is not an array, using empty array');
    } else {
      log('[ChatGPT Extractor] 📊 Processing ' + messages.length + ' messages for JSON assembly');
    }

    // Calculate rich content summary
    var richContentSummary = {
      totalCodeBlocks: 0,
      totalImages: 0,
      totalFiles: 0,
      totalTables: 0,
      totalFormulas: 0,
      totalArtifacts: 0,
      messagesWithRichContent: 0
    };

    messages.forEach(function (msg) {
      if (msg.contentType === 'rich') {
        richContentSummary.messagesWithRichContent++;
        if (msg.codeBlocks) richContentSummary.totalCodeBlocks += msg.codeBlocks.length;
        if (msg.images) richContentSummary.totalImages += msg.images.length;
        if (msg.files) richContentSummary.totalFiles += msg.files.length;
        if (msg.tables) richContentSummary.totalTables += msg.tables.length;
        if (msg.formulas) richContentSummary.totalFormulas += msg.formulas.length;
        if (msg.artifacts) richContentSummary.totalArtifacts += msg.artifacts.length;
      }
    });

    // Build complete payload with all required fields
    var payload = {
      success: true,  // Always set success flag
      sessionId: sessionId,
      chatId: chatId || null,  // Ensure chatId is included
      platform: CONFIG.PLATFORM,
      extractorVersion: CONFIG.VERSION,
      extractedAt: Date.now(),
      url: window.location.href,
      messageCount: messages.length,
      messages: messages,  // Ensure messages array is always present
      richContentSummary: richContentSummary,
      userId: userInfo.user_id || userInfo.userId || null,
      user: userInfo
    };

    // Validate message structure
    payload.messages = payload.messages.map(function (msg, idx) {
      // Ensure each message has required fields
      if (!msg.role) msg.role = 'unknown';
      if (!msg.content) msg.content = '';
      if (typeof msg.timestamp !== 'number') msg.timestamp = Date.now() - (messages.length - idx) * CONFIG.TIMESTAMP_INTERVAL_MS;
      if (typeof msg.index !== 'number') msg.index = idx;
      return msg;
    });

    if (CONFIG.VERBOSE) {
      Logger.success('Assembled conversation payload: sessionId=' + payload.sessionId + ', messageCount=' + payload.messageCount);
      if (richContentSummary.messagesWithRichContent > 0) {
        Logger.log('Rich content: ' + richContentSummary.totalCodeBlocks + ' code blocks, ' +
          richContentSummary.totalImages + ' images, ' +
          richContentSummary.totalTables + ' tables');
      }
    }

    // Console message for JSON extraction
    log('[ChatGPT Extractor] ✅ JSON payload assembled: ' + payload.messageCount + ' messages, sessionId: ' + payload.sessionId);
    if (richContentSummary.messagesWithRichContent > 0) {
      log('[ChatGPT Extractor] 📦 Rich content found: ' + richContentSummary.totalCodeBlocks + ' code blocks, ' +
        richContentSummary.totalImages + ' images, ' +
        richContentSummary.totalTables + ' tables');
    }

    return payload;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MAIN EXTRACTION FUNCTION
  // ═══════════════════════════════════════════════════════════════════════════

  // Per-page throttle to keep the host page responsive. ChatGPT's router
  // fires history.pushState many times per second on the home / new-chat URL
  // and each one used to trigger a full DOM scan + Strategy 1-6 + fallback.
  // The throttle:
  //   - bails out instantly on non-conversation URLs (no /c/<id> in URL),
  //   - rate-limits same-URL scans to once per MIN_INTERVAL_MS,
  //   - freezes extraction for FREEZE_MS after a streak of empty results
  //     (the DOM isn't ready yet — keep waiting silently).
  var __VELOCITY_THROTTLE = {
    lastAt: 0,
    lastUrl: null,
    lastResult: null,
    emptyStreak: 0,
    frozenUntil: 0,
    MIN_INTERVAL_MS: 800,
    EMPTY_STREAK_LIMIT: 3,
    FREEZE_MS: 30000
  };

  function extractConversation() {
    var now = Date.now();
    var currentUrl = (typeof window !== 'undefined' && window.location) ? window.location.href : '';

    // 0a. Skip on non-conversation URLs (home / new-chat / settings).
    if (!DataCache.isConversationPage()) {
      return { success: false, error: 'not_a_conversation_page', messages: [] };
    }

    // Reset throttle counters on URL change.
    if (currentUrl !== __VELOCITY_THROTTLE.lastUrl) {
      __VELOCITY_THROTTLE.lastUrl = currentUrl;
      __VELOCITY_THROTTLE.lastAt = 0;
      __VELOCITY_THROTTLE.emptyStreak = 0;
      __VELOCITY_THROTTLE.frozenUntil = 0;
      __VELOCITY_THROTTLE.lastResult = null;
    }

    // 0b. While frozen (after repeated empties), short-circuit until DOM signals.
    if (now < __VELOCITY_THROTTLE.frozenUntil) {
      return __VELOCITY_THROTTLE.lastResult || { success: false, error: 'frozen', messages: [] };
    }

    // 0c. Rate-limit duplicate scans of the same URL.
    if (__VELOCITY_THROTTLE.lastResult && now - __VELOCITY_THROTTLE.lastAt < __VELOCITY_THROTTLE.MIN_INTERVAL_MS) {
      return __VELOCITY_THROTTLE.lastResult;
    }
    __VELOCITY_THROTTLE.lastAt = now;

    function __velocityFinalize(result) {
      __VELOCITY_THROTTLE.lastResult = result;
      var hasMessages = result && result.messages && result.messages.length > 0;
      if (hasMessages) {
        __VELOCITY_THROTTLE.emptyStreak = 0;
      } else {
        __VELOCITY_THROTTLE.emptyStreak++;
        if (__VELOCITY_THROTTLE.emptyStreak >= __VELOCITY_THROTTLE.EMPTY_STREAK_LIMIT) {
          __VELOCITY_THROTTLE.frozenUntil = Date.now() + __VELOCITY_THROTTLE.FREEZE_MS;
          __VELOCITY_THROTTLE.emptyStreak = 0;
        }
      }
      return result;
    }

    Logger.info('═══════════════════════════════════════════════════════════');
    Logger.info('Starting ChatGPT Conversation Extraction');
    Logger.info('═══════════════════════════════════════════════════════════');

    var startTime = performance.now();

    try {
      // Step 1: Find conversation root
      var root = findConversationRoot();
      if (!root) {
        Logger.error('Could not find conversation root');
        return __velocityFinalize({ success: false, error: 'No conversation root found', messages: [] });
      }

      // Step 2: Collect candidates
      var candidates = collectMessageCandidates(root);
      if (candidates.length === 0) {
        Logger.warn('No message candidates found');
        return __velocityFinalize({ success: false, error: 'No message candidates found', messages: [] });
      }

      // Step 3: Filter real messages
      var realMessages = filterRealMessages(candidates);
      if (realMessages.length === 0) {
        Logger.warn('⚠️ No real messages after filtering');
        Logger.warn('   Trying alternative collection strategy...');

        // Fallback: Try more aggressive collection
        var fallbackCandidates = [];

        // Strategy A: Look for any article or div with substantial content (updated)
        var articles = root.querySelectorAll('article, [role="article"], [data-testid*="conversation-item"], [class*="conversation-turn"]');
        articles.forEach(function (art) {
          var text = extractTextContent(art);
          if (text && text.length >= 10 && !isNoiseElement(art)) {
            fallbackCandidates.push(art);
          }
        });

        // Strategy B: Look for elements with message-like structure (updated for current ChatGPT)
        var messageLike = root.querySelectorAll('[class*="message"], [class*="turn"], [class*="chat"], [class*="agent-turn"], [class*="user-turn"], [data-testid*="chat-message"]');
        messageLike.forEach(function (el) {
          var text = extractTextContent(el);
          if (text && text.length >= 10 && !isNoiseElement(el)) {
            fallbackCandidates.push(el);
          }
        });

        // Strategy C: Look for any div with data attributes that might indicate messages (updated)
        var dataElements = root.querySelectorAll('[data-message-id], [data-message-author-role], [data-testid*="message"], [data-testid*="conversation-turn"], [data-testid*="turn"]');
        dataElements.forEach(function (el) {
          var text = extractTextContent(el);
          if (text && text.length >= 10 && !isNoiseElement(el)) {
            fallbackCandidates.push(el);
          }
        });

        // Strategy D: Look for ChatGPT specific message patterns (added)
        var chatGptPatterns = root.querySelectorAll('[class*="message-wrapper"], [class*="message-content"], [data-testid*="message-content"]');
        chatGptPatterns.forEach(function (el) {
          var text = extractTextContent(el);
          if (text && text.length >= 10 && !isNoiseElement(el)) {
            fallbackCandidates.push(el);
          }
        });

        // Remove duplicates
        var seen = new Set();
        var uniqueFallback = [];
        fallbackCandidates.forEach(function (cand) {
          if (!seen.has(cand)) {
            seen.add(cand);
            uniqueFallback.push(cand);
          }
        });

        if (uniqueFallback.length > 0) {
          Logger.log('   Found ' + uniqueFallback.length + ' fallback candidates');
          realMessages = uniqueFallback;
        } else {
          Logger.error('❌ No messages found even with fallback strategies');
          Logger.error('   This might be a new chat or the page structure changed');
          Logger.error('   Candidates found: ' + candidates.length);
          Logger.error('   💡 Try waiting a few seconds and extracting again');
          return __velocityFinalize({ success: false, error: 'No real messages found after all strategies', messages: [], candidatesFound: candidates.length });
        }
      }

      // Sort by DOM position
      realMessages.sort(function (a, b) {
        var position = a.compareDocumentPosition(b);
        if (position & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
        if (position & Node.DOCUMENT_POSITION_PRECEDING) return 1;
        return 0;
      });

      // Step 4 & 5: Process each message with rich content
      var timestamps = generateSyntheticTimestamps(realMessages.length);
      var processedMessages = realMessages.map(function (element, index) {
        var role = detectMessageRole(element, index);
        var content = extractTextContent(element);
        var richContent = extractRichContent(element);

        var message = {
          role: role,
          content: content,
          timestamp: timestamps[index],
          index: index,
          contentType: richContent.hasRichContent ? 'rich' : 'plain'
        };

        // Add rich content if present
        if (richContent.hasRichContent) {
          if (richContent.codeBlocks.length > 0) {
            message.codeBlocks = richContent.codeBlocks;
          }
          if (richContent.images.length > 0) {
            message.images = richContent.images;
          }
          if (richContent.files.length > 0) {
            message.files = richContent.files;
          }
          if (richContent.tables.length > 0) {
            message.tables = richContent.tables;
          }
          if (richContent.formulas.length > 0) {
            message.formulas = richContent.formulas;
          }
          if (richContent.artifacts.length > 0) {
            message.artifacts = richContent.artifacts;
          }
        }

        return message;
      });

      // Filter out JavaScript noise messages that slipped through
      var filteredMessages = processedMessages.filter(function (msg) {
        if (isJavaScriptNoise(msg.content)) {
          Logger.warn('Filtered JS noise message: ' + msg.content.substring(0, 50) + '...');
          return false;
        }
        return true;
      });

      // Re-index messages after filtering
      filteredMessages.forEach(function (msg, idx) {
        msg.index = idx;
      });

      // Step 6: Assemble payload
      var payload = assembleConversationPayload(filteredMessages);

      // VALIDATION: Ensure all required fields are present
      if (!payload.success) {
        payload.success = true; // Ensure success flag is set
      }
      if (!payload.messages || !Array.isArray(payload.messages)) {
        payload.messages = filteredMessages || [];
      }
      if (typeof payload.messageCount !== 'number') {
        payload.messageCount = payload.messages.length;
      }
      if (!payload.chatId) {
        payload.chatId = DataCache.getChatIdFromUrl();
      }
      if (!payload.url) {
        payload.url = window.location.href;
      }
      if (!payload.platform) {
        payload.platform = CONFIG.PLATFORM;
      }

      var endTime = performance.now();
      Logger.success('Extraction completed in ' + (endTime - startTime).toFixed(2) + 'ms');
      Logger.info('═══════════════════════════════════════════════════════════');

      // Console message for successful extraction
      log('[ChatGPT Extractor] ✅ Extraction completed successfully: ' + payload.messageCount + ' messages extracted in ' + (endTime - startTime).toFixed(2) + 'ms');
      log('[ChatGPT Extractor] 📄 JSON ready - Use showJSON() to view formatted output');

      return __velocityFinalize(payload);

    } catch (error) {
      Logger.error('Extraction failed:', error);
      console.error('[ChatGPT Extractor] ❌ JSON extraction failed:', error);
      return __velocityFinalize({ success: false, error: error.message, messages: [] });
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DIAGNOSTIC UTILITIES
  // ═══════════════════════════════════════════════════════════════════════════

  function runDiagnostics() {
    Logger.info('═══════════════════════════════════════════════════════════');
    Logger.info('🔬 RUNNING DOM DIAGNOSTICS');
    Logger.info('═══════════════════════════════════════════════════════════');

    Logger.log('Page URL:', window.location.href);
    Logger.log('Document ready state:', document.readyState);

    var main = document.querySelector('main');
    Logger.log('Main element exists:', !!main);

    var messageAttrs = document.querySelectorAll('[data-message-author-role]');
    Logger.log('Elements with data-message-author-role:', messageAttrs.length);

    if (messageAttrs.length > 0) {
      Logger.log('Role values found:');
      var roles = {};
      messageAttrs.forEach(function (el) {
        var role = el.getAttribute('data-message-author-role');
        roles[role] = (roles[role] || 0) + 1;
      });
      Logger.table(roles);
    }

    var articles = document.querySelectorAll('article');
    Logger.log('Article elements:', articles.length);

    Logger.group('Potential Message Containers Analysis');

    var analysisData = [];
    var root = findConversationRoot();
    var candidates = collectMessageCandidates(root);

    candidates.slice(0, 20).forEach(function (el, i) {
      var text = extractTextContent(el);
      analysisData.push({
        index: i,
        tagName: el.tagName,
        hasRoleAttr: !!el.getAttribute('data-message-author-role'),
        roleValue: el.getAttribute('data-message-author-role') || 'N/A',
        textPreview: text.substring(0, 50) + (text.length > 50 ? '...' : ''),
        textLength: text.length,
        height: el.offsetHeight,
        hasCodeBlock: !!el.querySelector('pre, code'),
        hasList: !!el.querySelector('ul, ol')
      });
    });

    Logger.table(analysisData);
    Logger.groupEnd();

    Logger.group('DOM Structure Sample');
    if (candidates.length > 0) {
      var sample = candidates[0];
      Logger.log('Tag:', sample.tagName);
      Logger.log('Classes:', sample.className);
      Logger.log('ID:', sample.id || 'N/A');
      var dataAttrs = Array.from(sample.attributes)
        .filter(function (attr) { return attr.name.indexOf('data-') === 0; })
        .map(function (attr) { return attr.name + '="' + attr.value + '"'; })
        .join(', ');
      Logger.log('Data attributes:', dataAttrs || 'None');
      Logger.log('Parent tag:', sample.parentElement ? sample.parentElement.tagName : 'N/A');
      Logger.log('Children count:', sample.children.length);
    }
    Logger.groupEnd();

    Logger.info('═══════════════════════════════════════════════════════════');
    Logger.info('Diagnostics complete.');
    Logger.info('═══════════════════════════════════════════════════════════');

    return {
      pageUrl: window.location.href,
      hasMain: !!main,
      messageAttrCount: messageAttrs.length,
      articleCount: articles.length,
      candidateCount: candidates.length,
      analysisData: analysisData
    };
  }

  function checkStatus() {
    var messageAttrs = document.querySelectorAll('[data-message-author-role]');
    var articles = document.querySelectorAll('article');

    Logger.info('Quick Status Check:');
    Logger.log('• Messages with role attribute: ' + messageAttrs.length);
    Logger.log('• Article elements: ' + articles.length);
    Logger.log('• URL: ' + window.location.href);

    return { messageAttrCount: messageAttrs.length, articleCount: articles.length };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MUTATION OBSERVER
  // ═══════════════════════════════════════════════════════════════════════════

  var conversationObserver = null;
  var lastMessageCount = 0;
  var debounceTimer = null;

  function startConversationObserver(callback) {
    if (conversationObserver) {
      Logger.warn('Observer already running');
      return;
    }

    Logger.info('Starting conversation observer...');

    var root = findConversationRoot();
    if (!root) {
      Logger.error('Cannot start observer: no conversation root');
      return;
    }

    conversationObserver = new MutationObserver(function (mutations) {
      if (debounceTimer) clearTimeout(debounceTimer);

      debounceTimer = setTimeout(function () {
        var result = extractConversation();

        if (result.success && result.messageCount !== lastMessageCount) {
          Logger.log('Message count changed: ' + lastMessageCount + ' → ' + result.messageCount);
          lastMessageCount = result.messageCount;

          if (callback && typeof callback === 'function') {
            callback(result);
          }
        }
      }, 500);
    });

    conversationObserver.observe(root, { childList: true, subtree: true, characterData: true });
    Logger.success('Conversation observer started');
  }

  function stopConversationObserver() {
    if (conversationObserver) {
      conversationObserver.disconnect();
      conversationObserver = null;
      Logger.info('Conversation observer stopped');
    }
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SIDEBAR EXTRACTION
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Extracts all chat history items from the sidebar
   * 
   * @returns {Object} Sidebar data with chat list
   */
  function extractSidebar() {
    Logger.info('═══════════════════════════════════════════════════════════');
    Logger.info('Extracting Sidebar Chat History');
    Logger.info('═══════════════════════════════════════════════════════════');

    var startTime = performance.now();

    try {
      // Find nav element
      var nav = document.querySelector('nav');
      if (!nav) {
        Logger.error('Could not find nav element');
        return { success: false, error: 'No sidebar found', chats: [] };
      }

      // Find all chat links
      var chatLinks = nav.querySelectorAll('a[href*="/c/"]');
      Logger.log('Found ' + chatLinks.length + ' chat links');

      if (chatLinks.length === 0) {
        Logger.warn('No chat links found in sidebar');
        return { success: false, error: 'No chats found', chats: [] };
      }

      // Extract chat data
      var chats = [];
      var seenIds = new Set();

      chatLinks.forEach(function (link, index) {
        var href = link.getAttribute('href') || '';
        var title = link.innerText ? link.innerText.trim() : '';

        // Extract chat ID from href (e.g., /c/695386be-fbbc-8324-8cac-0a519c3330c0)
        var chatIdMatch = href.match(/\/c\/([a-f0-9-]+)/i);
        var chatId = chatIdMatch ? chatIdMatch[1] : null;

        // Skip if no valid chat ID or duplicate
        if (!chatId || seenIds.has(chatId)) {
          return;
        }
        seenIds.add(chatId);

        // Skip if title is empty or too short
        if (!title || title.length < 2) {
          return;
        }

        // Build full URL
        var fullUrl = 'https://chatgpt.com' + href;

        // Check if this is the current active chat
        var isActive = window.location.pathname === href;

        chats.push({
          index: chats.length,
          chatId: chatId,
          title: title,
          href: href,
          url: fullUrl,
          isActive: isActive
        });
      });

      var endTime = performance.now();

      var payload = {
        success: true,
        extractedAt: Date.now(),
        platform: CONFIG.PLATFORM,
        totalChats: chats.length,
        currentUrl: window.location.href,
        chats: chats
      };

      Logger.success('Extracted ' + chats.length + ' chats in ' + (endTime - startTime).toFixed(2) + 'ms');
      Logger.info('═══════════════════════════════════════════════════════════');

      return payload;

    } catch (error) {
      Logger.error('Sidebar extraction failed:', error);
      return { success: false, error: error.message, chats: [] };
    }
  }

  /**
   * Finds a specific chat by title or ID
   * 
   * @param {string} query - Title or ID to search for
   * @returns {Object|null} Matching chat or null
   */
  function findChat(query) {
    if (!query) {
      Logger.error('No search query provided');
      return null;
    }

    var sidebarData = extractSidebar();
    if (!sidebarData.success) {
      return null;
    }

    var queryLower = query.toLowerCase();

    // Search by ID first (exact match)
    var byId = sidebarData.chats.find(function (chat) {
      return chat.chatId === query || chat.chatId.indexOf(query) === 0;
    });
    if (byId) {
      Logger.success('Found chat by ID: ' + byId.title);
      return byId;
    }

    // Search by title (partial match)
    var byTitle = sidebarData.chats.find(function (chat) {
      return chat.title.toLowerCase().indexOf(queryLower) !== -1;
    });
    if (byTitle) {
      Logger.success('Found chat by title: ' + byTitle.title);
      return byTitle;
    }

    Logger.warn('No chat found matching: ' + query);
    return null;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // COMBINED EXTRACTION (CONVERSATION + SIDEBAR)
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Extracts BOTH the current conversation AND sidebar chat history
   * Returns a combined JSON payload
   * 
   * @returns {Object} Combined data with conversation and sidebar
   */
  function extractAll() {
    // Verbose: Extraction start banner
    if (CONFIG.VERBOSE) {
      Logger.info('═══════════════════════════════════════════════════════════');
      Logger.info('Extracting Full ChatGPT Data (Conversation + Sidebar)');
      Logger.info('═══════════════════════════════════════════════════════════');
    }

    var startTime = performance.now();

    // Extract current conversation
    var conversationData = extractConversation();

    // Extract sidebar
    var sidebarData = extractSidebar();

    var endTime = performance.now();

    // Build combined payload
    var payload = {
      success: true,
      extractedAt: Date.now(),
      extractionTime: (endTime - startTime).toFixed(2) + 'ms',
      platform: CONFIG.PLATFORM,
      extractorVersion: CONFIG.VERSION,
      url: window.location.href,

      // Current conversation
      conversation: {
        success: conversationData.success,
        sessionId: conversationData.sessionId || null,
        messageCount: conversationData.messageCount || 0,
        messages: conversationData.messages || [],
        error: conversationData.error || null
      },

      // Sidebar chat history
      sidebar: {
        success: sidebarData.success,
        totalChats: sidebarData.totalChats || 0,
        chats: sidebarData.chats || [],
        error: sidebarData.error || null
      }
    };

    // Show extraction summary
    log('[ChatGPT Extractor] ✅ Full extraction completed:');
    log('[ChatGPT Extractor]   - Conversation: ' + payload.conversation.messageCount + ' messages');
    log('[ChatGPT Extractor]   - Sidebar: ' + payload.sidebar.totalChats + ' chats');
    log('[ChatGPT Extractor]   - Time: ' + payload.extractionTime);
    log('[ChatGPT Extractor] 📄 JSON ready - Use showJSON() to view formatted output');

    // Verbose: Detailed summary
    if (CONFIG.VERBOSE) {
      Logger.info('═══════════════════════════════════════════════════════════');
    }

    return payload;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SMART TRACKING SYSTEM
  // ═══════════════════════════════════════════════════════════════════════════

  // Initialize Smart Trigger Manager (if available)
  var smartTrigger = null;
  if (typeof window.SmartTriggerManager !== 'undefined') {
    log('[ChatGPT Extractor] ✅ SmartTriggerManager found, initializing...');
    smartTrigger = new window.SmartTriggerManager({
      minWordCountDelta: 10,        // Minimum 10 new words for meaningful change
      minTimeBetweenUpdates: 1000,  // 1 second between updates
      maxUpdatesPerHour: 60,        // 60 updates per hour max (rate limiting)
      streamingDebounceTime: 1000,  // Wait 1 second after streaming
      minMessages: 5                // At least 5 messages for meaningful conversation
    });
    log('[ChatGPT Extractor] ✅ SmartTriggerManager initialized with settings:', {
      minWordCountDelta: 10,
      minTimeBetweenUpdates: 1000,
      maxUpdatesPerHour: 60,
      streamingDebounceTime: 1000,
      minMessages: 5
    });
    if (CONFIG.VERBOSE) {
      Logger.info('✅ Smart Trigger Manager initialized');
    }
  } else {
    if (CONFIG.VERBOSE) {
      Logger.warn('⚠️ Smart Trigger Manager not found - using basic triggering');
    }
  }

  var SmartTracker = {
    // Tracking state
    isTracking: false,
    urlObserver: null,
    domObserver: null,
    debounceTimer: null,
    streamingCheckTimer: null,

    /**
     * Start smart tracking - monitors URL changes, DOM mutations, and streaming
     */
    start: function (callback) {
      if (this.isTracking) {
        Logger.warn('Smart tracking already active');
        return;
      }

      // Verbose: Tracking start banner
      if (CONFIG.VERBOSE) {
        Logger.info('═══════════════════════════════════════════════════════════');
        Logger.info('🚀 Starting Smart Tracking System');
        Logger.info('═══════════════════════════════════════════════════════════');
      }

      var self = this;
      this.isTracking = true;

      // Initial state
      DataCache.currentUrl = window.location.href;
      DataCache.currentChatId = DataCache.getChatIdFromUrl();

      // 1. URL Change Detection (for chat navigation)
      this.startUrlWatcher(callback);

      // 2. DOM Mutation Observer (for new messages)
      this.startDomWatcher(callback);

      // 3. Initial extraction
      // initial_load is a special trigger - always allow (bypass SmartTriggerManager)
      // This ensures we capture the initial state regardless of throttling
      // Only run initial extraction when we're actually on a conversation page
      // (e.g. /c/<id>) — avoids hammering the main thread on home/new-chat URLs.
      if (DataCache.isConversationPage()) {
        this.performSmartExtraction(callback, 'initial_load');
      }

      // Verbose: Tracking details
      if (CONFIG.VERBOSE) {
        Logger.success('Smart tracking started');
        Logger.log('  • Watching URL changes');
        Logger.log('  • Watching DOM mutations');
        Logger.log('  • Streaming detection active');
      }
    },

    /**
     * Stop all tracking
     */
    stop: function () {
      if (!this.isTracking) return;

      // Restore original history methods
      if (this.originalPushState) {
        history.pushState = this.originalPushState;
        this.originalPushState = null;
      }
      if (this.originalReplaceState) {
        history.replaceState = this.originalReplaceState;
        this.originalReplaceState = null;
      }

      if (this.urlObserver) {
        // Remove URL listener
        window.removeEventListener('popstate', this.urlObserver);
        this.urlObserver = null;
      }

      if (this.visibilityObserver) {
        document.removeEventListener('visibilitychange', this.visibilityObserver);
        this.visibilityObserver = null;
      }

      if (this.domObserver) {
        this.domObserver.disconnect();
        this.domObserver = null;
      }

      if (this.debounceTimer) {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = null;
      }

      if (this.streamingCheckTimer) {
        clearInterval(this.streamingCheckTimer);
        this.streamingCheckTimer = null;
      }

      this.isTracking = false;
      Logger.info('Smart tracking stopped');
    },

    /**
     * Watch for URL changes (navigation between chats)
     * OPTIMIZED: Uses History API events instead of polling
     */
    startUrlWatcher: function (callback) {
      var self = this;
      var lastUrl = window.location.href;

      // Store original history methods
      var originalPushState = history.pushState;
      var originalReplaceState = history.replaceState;

      // Override pushState to detect SPA navigation
      history.pushState = function () {
        originalPushState.apply(history, arguments);
        var currentUrl = window.location.href;
        if (currentUrl !== lastUrl) {
          lastUrl = currentUrl;
          self.handleUrlChange(callback);
        }
      };

      // Override replaceState to detect SPA navigation
      history.replaceState = function () {
        originalReplaceState.apply(history, arguments);
        var currentUrl = window.location.href;
        if (currentUrl !== lastUrl) {
          lastUrl = currentUrl;
          self.handleUrlChange(callback);
        }
      };

      // Listen to popstate (back/forward navigation)
      this.urlObserver = function () {
        var currentUrl = window.location.href;
        if (currentUrl !== lastUrl) {
          lastUrl = currentUrl;
          self.handleUrlChange(callback);
        }
      };
      window.addEventListener('popstate', this.urlObserver, { passive: true });

      // Fallback: Check URL on visibility change (tab switch)
      this.visibilityObserver = function () {
        if (!document.hidden) {
          var currentUrl = window.location.href;
          if (currentUrl !== lastUrl) {
            lastUrl = currentUrl;
            self.handleUrlChange(callback);
          }
        }
      };
      document.addEventListener('visibilitychange', this.visibilityObserver, { passive: true });

      // Store references for cleanup
      this.originalPushState = originalPushState;
      this.originalReplaceState = originalReplaceState;
    },

    /**
     * Handle URL change event with retry mechanism
     */
    handleUrlChange: function (callback) {
      var oldChatId = DataCache.currentChatId;
      var newChatId = DataCache.getChatIdFromUrl();
      var newUrl = window.location.href;

      // Verbose: URL change
      if (CONFIG.VERBOSE) {
        Logger.info('URL changed: ' + newUrl);
      }

      DataCache.currentUrl = newUrl;
      DataCache.currentChatId = newChatId;

      if (newChatId !== oldChatId && newChatId) {
        // Different chat - extract with retry mechanism
        // Verbose: Chat change
        if (CONFIG.VERBOSE) {
          Logger.log('Chat changed: ' + (oldChatId || 'home') + ' → ' + newChatId);
        }

        // Check if this chat has missing messages in store
        var existingChat = SessionStore.getConversation(newChatId);
        var needsFix = existingChat && existingChat.messageCount > 0 &&
          (!existingChat.messages || existingChat.messages.length === 0);

        if (needsFix) {
          Logger.warn('⚠️ Chat has missing messages! Auto-fixing...');
          Logger.warn('   Expected: ' + existingChat.messageCount + ' messages');
        }

        var self = this;
        var retryCount = 0;
        // Reduced retry pressure: prior 5×1000ms / 8×500ms scans were the
        // biggest source of host-page lag on ChatGPT new-chat URLs. The
        // extractConversation() throttle further dedupes within MIN_INTERVAL_MS.
        var maxRetries = needsFix ? 4 : 3;
        var retryDelay = needsFix ? 750 : 1200;
        var targetChatId = newChatId;

        function tryExtract() {
          setTimeout(function () {
            // Abort the retry loop if the user navigated away from the chat
            // mid-cycle — otherwise we'd extract for a chat that's no longer
            // visible.
            if (DataCache.getChatIdFromUrl() !== targetChatId) {
              if (CONFIG.VERBOSE) {
                Logger.log('Abort retry: URL left chat ' + targetChatId);
              }
              return;
            }

            var conversationData = extractConversation();

            if (conversationData.success && conversationData.messages && conversationData.messages.length > 0) {
              Logger.success('✅ Messages found (' + conversationData.messages.length + '), proceeding with save');
              self.performSmartExtraction(callback, needsFix ? 'fixing_missing' : 'chat_changed');
            } else if (retryCount < maxRetries) {
              retryCount++;
              if (CONFIG.VERBOSE) {
                Logger.log('⏳ No messages yet, retry ' + retryCount + '/' + maxRetries + ' in ' + retryDelay + 'ms');
              }
              tryExtract();
            } else {
              if (CONFIG.VERBOSE) {
                Logger.warn('⚠️ Max retries reached, extracting anyway (chat might be empty)');
              }
              self.performSmartExtraction(callback, 'chat_changed');
            }
          }, retryDelay);
        }

        tryExtract();
      } else if (newChatId === oldChatId && newChatId) {
        // Same chat - just update if needed (only when there IS a chat;
        // root/home pushState should not trigger extraction).
        // url_refresh can use SmartTriggerManager for filtering
        if (smartTrigger) {
          var conversationData = extractConversation();
          var changeEvent = {
            trigger: 'url_refresh',
            messages: conversationData.messages || [],
            data: {
              conversation: conversationData
            }
          };
          var self = this;
          smartTrigger.onDOMChange(changeEvent, callback, function (changeEvent, callback) {
            self.performSmartExtraction(callback, 'url_refresh');
          });
        } else {
          this.performSmartExtraction(callback, 'url_refresh');
        }
      }
    },

    /**
     * Watch for DOM mutations (new messages)
     * OPTIMIZED: Filters mutations to only process relevant changes
     */
    startDomWatcher: function (callback) {
      var self = this;

      // Find the conversation container (more specific than document.body)
      var root = findConversationRoot();

      // Helper function to check if mutation is in conversation area
      function isInConversationArea(target) {
        if (!target || !target.nodeType) return false;

        // Check if target is within conversation root
        if (root.contains(target)) {
          // Filter out common non-message areas
          var element = target.nodeType === 1 ? target : target.parentElement;
          if (!element) return true; // Text node, allow it

          // Skip mutations in sidebar, navigation, or other UI elements
          var isSidebar = element.closest && (
            element.closest('[class*="sidebar"]') ||
            element.closest('[class*="nav"]') ||
            element.closest('[role="navigation"]') ||
            element.closest('[data-testid*="sidebar"]')
          );

          if (isSidebar) return false;

          // Allow mutations in message-like containers
          var isMessageArea = element.closest && (
            element.closest('[data-message-author-role]') ||
            element.closest('article') ||
            element.closest('[data-message-id]') ||
            element.closest('[data-testid*="message"]') ||
            element.closest('[data-testid*="turn"]')
          );

          return isMessageArea !== null;
        }

        return false;
      }

      this.domObserver = new MutationObserver(function (mutations) {
        // OPTIMIZATION: Filter mutations before processing
        var relevantMutations = mutations.filter(function (mutation) {
          return isInConversationArea(mutation.target);
        });

        // Skip if no relevant mutations
        if (relevantMutations.length === 0) {
          return;
        }

        // Debounce only relevant mutations
        if (self.debounceTimer) {
          clearTimeout(self.debounceTimer);
        }

        self.debounceTimer = setTimeout(function () {
          self.handleDomChange(callback, relevantMutations);
        }, CONFIG.DEBOUNCE_MS);
      });

      // OPTIMIZATION: Don't watch attribute changes (reduces events)
      this.domObserver.observe(root, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: false,  // Don't watch attribute changes
        attributeOldValue: false
      });
    },

    /**
     * Handle DOM mutation event
     */
    handleDomChange: function (callback, mutations) {
      var self = this;

      // Check if streaming
      if (DataCache.checkIsStreaming()) {
        // Verbose: Streaming detection
        if (CONFIG.VERBOSE) {
          Logger.log('Streaming detected - waiting for completion...');
        }
        DataCache.isStreaming = true;

        // Wait for streaming to complete
        DataCache.waitForStreamingComplete(function () {
          DataCache.isStreaming = false;
          // Use SmartTriggerManager if available, otherwise direct call
          if (smartTrigger) {
            log('[ChatGPT Extractor] 🎯 Using SmartTriggerManager for streaming_complete');
            // Extract data first to check if we should trigger
            var conversationData = extractConversation();
            var changeEvent = {
              trigger: 'streaming_complete',
              messages: conversationData.messages || [],
              data: {
                conversation: conversationData
              }
            };
            log('[ChatGPT Extractor] 📊 Change event for SmartTriggerManager:', {
              trigger: changeEvent.trigger,
              messageCount: changeEvent.messages.length,
              hasConversationData: !!changeEvent.data?.conversation
            });
            smartTrigger.onDOMChange(changeEvent, callback, function (changeEvent, callback) {
              self.performSmartExtraction(callback, 'streaming_complete');
            });
          } else {
            self.performSmartExtraction(callback, 'streaming_complete');
          }
        });
        return;
      }

      // Not streaming - use SmartTriggerManager if available
      if (smartTrigger) {
        log('[ChatGPT Extractor] 🎯 Using SmartTriggerManager for DOM change');
        // Extract data first to check if we should trigger
        var conversationData = extractConversation();
        var changeEvent = {
          trigger: 'dom_change',
          messages: conversationData.messages || [],
          data: {
            conversation: conversationData
          }
        };
        smartTrigger.onDOMChange(changeEvent, callback, function (changeEvent, callback) {
          self.performSmartExtraction(callback, 'dom_change');
        });
      } else {
        // Fallback to direct call if SmartTriggerManager not available
        this.performSmartExtraction(callback, 'dom_change');
      }
    },

    /**
     * Perform extraction with caching and change detection
     */
    performSmartExtraction: function (callback, trigger) {
      var chatId = DataCache.currentChatId;

      // Cheap early-out: when we're not on a conversation page AND have no
      // cached chat, skip the heavy DOM scans / payload assembly / upsert path
      // entirely. Avoids extraction storms on home/new-chat URLs where every
      // pushState would otherwise generate a fake `session_*` row.
      if (!chatId && !DataCache.isConversationPage()) {
        return;
      }

      // Verbose: Extraction trigger
      if (CONFIG.VERBOSE) {
        Logger.log('Smart extraction triggered by: ' + trigger);
      }

      // Extract fresh data
      var conversationData = extractConversation();
      var sidebarData = extractSidebar();

      // Check what changed (for DataCache)
      var conversationChanged = DataCache.hasConversationChanged(chatId, conversationData);
      var sidebarChanged = DataCache.hasSidebarChanged(sidebarData);

      // ═══════════════════════════════════════════════════════════════════════
      // UPDATE SESSION STORE (Cumulative - never deletes, only adds/updates)
      // ═══════════════════════════════════════════════════════════════════════
      var sessionUpdate = null;

      // Generate a fallback chatId if URL doesn't contain one
      if (!chatId) {
        // Create a unique session ID based on URL and timestamp
        var urlHash = btoa(window.location.href).replace(/[^a-zA-Z0-9]/g, '').substr(0, 16);
        chatId = 'session_' + urlHash + '_' + Date.now();
        log('[SmartTracker] Generated fallback chatId:', chatId);
      }

      if (chatId && conversationData.success) {
        // ALWAYS save - upsertConversation will handle empty messages correctly
        // It won't overwrite existing messages with empty arrays
        sessionUpdate = SessionStore.upsertConversation(chatId, conversationData);

        if (conversationData.messages && conversationData.messages.length > 0) {

          // ═══════════════════════════════════════════════════════════════════════
          // ESSENCE SYSTEM INTEGRATION: Trigger essence creation if needed
          // (MAIN world has no chrome.runtime - use bridge to ISOLATED world)
          // ═══════════════════════════════════════════════════════════════════════
          try {
            window.postMessage({
              type: 'CONTEXT_ENGINE_BRIDGE',
              action: 'handleMessagesExtracted',
              chatId: chatId,
              messages: conversationData.messages,
              platform: CONFIG.PLATFORM || 'chatgpt',
              messageCount: conversationData.messages.length,
              sessionId: conversationData.sessionId
            }, '*');
          } catch (err) {
            error('[ChatGPT Extractor] ❌ Exception sending message:', err);
          }
          // ═══════════════════════════════════════════════════════════════════════
        } else if (conversationData.messageCount > 0) {
          Logger.warn('⚠️ Chat has count=' + conversationData.messageCount + ' but no messages extracted yet');
          Logger.warn('   Will retry on next visit or DOM change');
        }
      }

      // Update sidebar snapshot in SessionStore
      if (sidebarData.success) {
        SessionStore.updateSidebar(sidebarData);
      }
      // ═══════════════════════════════════════════════════════════════════════

      if (!conversationChanged && !sidebarChanged && trigger !== 'initial_load') {
        // Verbose: No changes
        if (CONFIG.VERBOSE) {
          Logger.log('No changes detected - skipping callback');
        }
        return;
      }

      // Update DataCache (for efficiency/change detection)
      if (conversationChanged && chatId) {
        DataCache.setConversationCache(chatId, conversationData);
      }
      if (sidebarChanged) {
        DataCache.setSidebarCache(sidebarData);
      }

      // Build change report
      var changeReport = {
        trigger: trigger,
        timestamp: Date.now(),
        chatId: chatId,
        url: window.location.href,
        changes: {
          conversation: conversationChanged,
          sidebar: sidebarChanged
        },
        data: {
          conversation: conversationData,
          sidebar: sidebarData
        },
        delta: null,
        // Include session update info
        sessionUpdate: sessionUpdate,
        sessionStats: SessionStore.stats
      };

      // Calculate delta for conversation (new messages)
      if (conversationChanged && chatId) {
        var cached = DataCache.getConversationCache(chatId);
        if (cached && cached.data && conversationData.messages) {
          var oldCount = cached.data.messageCount || 0;
          var newCount = conversationData.messageCount || 0;

          if (newCount > oldCount) {
            changeReport.delta = {
              type: 'new_messages',
              count: newCount - oldCount,
              newMessages: conversationData.messages.slice(oldCount)
            };
          }
        }
      }

      // Emit event
      DataCache.emit(trigger, changeReport);

      // Call user callback
      if (typeof callback === 'function') {
        try {
          callback(changeReport);
        } catch (e) {
          Logger.error('Callback error:', e);
        }
      }

      // Log summary
      var summary = [];
      if (conversationChanged) summary.push('conversation');
      if (sidebarChanged) summary.push('sidebar');
      // Verbose: Extraction summary
      if (CONFIG.VERBOSE) {
        Logger.success('Extraction complete - changed: ' + (summary.join(', ') || 'none'));
      }
    },

    /**
     * Get tracking status
     */
    getStatus: function () {
      return {
        isTracking: this.isTracking,
        isStreaming: DataCache.isStreaming,
        currentChatId: DataCache.currentChatId,
        currentUrl: DataCache.currentUrl,
        cache: DataCache.getStats()
      };
    }
  };

  /**
   * Smart extract with caching - only extracts if data changed
   * @param {Object} options - Options
   * @param {boolean} options.force - Force extraction even if cached
   * @returns {Object} Extraction result with change info
   */
  function smartExtract(options) {
    options = options || {};
    var force = options.force || false;

    var chatId = DataCache.getChatIdFromUrl();

    // Check cache first (unless forced)
    if (!force && chatId) {
      var cached = DataCache.getConversationCache(chatId);
      if (cached) {
        Logger.log('Returning cached data for: ' + chatId);
        return {
          fromCache: true,
          cacheAge: Date.now() - cached.timestamp,
          data: cached.data
        };
      }
    }

    // Extract fresh
    var conversationData = extractConversation();
    var sidebarData = extractSidebar();

    // Update caches
    if (chatId && conversationData.success) {
      DataCache.setConversationCache(chatId, conversationData);
    }
    if (sidebarData.success) {
      DataCache.setSidebarCache(sidebarData);
    }

    return {
      fromCache: false,
      data: {
        conversation: conversationData,
        sidebar: sidebarData
      }
    };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // VALIDATION HELPERS (for testing selector updates)
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Test the updated ChatGPT selectors to ensure they work with current DOM
   */
  function testUpdatedSelectors() {
    log('🧪 Testing updated ChatGPT selectors...');

    var root = findConversationRoot();
    log('📍 Conversation root found:', !!root, root ? root.tagName : 'none');

    var results = {
      strategy1: document.querySelectorAll('[data-message-author-role]').length,
      strategy2: document.querySelectorAll('[data-message-id], [data-testid*="message"], [data-testid*="conversation-turn"], [data-testid*="turn"]').length,
      strategy3: document.querySelectorAll('article, [data-testid*="conversation-item"], [class*="conversation-turn"], [class*="message-wrapper"]').length,
      strategy4: document.querySelectorAll('[data-testid*="turn"], [class*="turn"], [data-testid*="conversation-turn"], [class*="message-turn"]').length,
      strategy5: document.querySelectorAll('[data-role], [role="article"], [role="row"], [data-testid*="message"], [class*="message"]').length,
      strategy55: document.querySelectorAll('[class*="agent-turn"], [class*="user-turn"], [data-testid*="chat-message"], [class*="chat-message"]').length
    };

    log('📊 Selector results:', results);

    var totalCandidates = Object.values(results).reduce(function(sum, count) { return sum + count; }, 0);
    log('📈 Total candidates found:', totalCandidates);

    if (totalCandidates > 0) {
      log('✅ Updated selectors are finding elements!');
    } else {
      log('❌ No candidates found - selectors may need further updates');
    }

    return results;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // EXPOSE API
  // ═══════════════════════════════════════════════════════════════════════════

  window.VelocityChatGPTExtractor = {
    // ★ Smart Tracking (Recommended)
    startTracking: function (callback) {
      SmartTracker.start(callback);
    },
    stopTracking: function () {
      SmartTracker.stop();
    },
    smartExtract: smartExtract,
    getTrackingStatus: function () {
      var status = SmartTracker.getStatus();
      // Add SmartTriggerManager status if available
      if (smartTrigger) {
        status.smartTrigger = smartTrigger.getStatus();
      }
      return status;
    },
    // Smart Trigger Manager access
    getSmartTriggerStatus: function () {
      return smartTrigger ? smartTrigger.getStatus() : null;
    },
    getSmartTriggerAnalytics: function () {
      return smartTrigger ? smartTrigger.getAnalytics() : null;
    },
    resetSmartTriggerAnalytics: function () {
      if (smartTrigger) {
        smartTrigger.resetAnalytics();
        return true;
      }
      return false;
    },

    // ★★ Session Store (Cumulative Data - Cross-Tab Synced!)
    session: {
      // Get all accumulated data as JSON
      export: function () { return SessionStore.exportSession(); },
      // Get summary (chat list without full messages)
      summary: function () { return SessionStore.getSummary(); },
      // Get specific conversation from session
      getChat: function (chatId) { return SessionStore.getConversation(chatId); },
      // Get all conversations (array)
      getAllChats: function () { return SessionStore.getAllConversations(); },
      // Get current session stats
      stats: function () { return SessionStore.stats; },
      // Get session ID
      getId: function () { return SessionStore.sessionId; },
      // Reset session completely (new session ID)
      reset: function () { SessionStore.reset(); },
      // Clear accumulated data (keep session)
      clear: function () { SessionStore.clear(); },
      // Force sync from localStorage
      forceSync: function () { SessionStore.forceSync(); },
      // Get sync status
      syncStatus: function () { return SessionStore.getSyncStatus(); },

      // ★ FOR ENHANCEMENT - Get stored content (not fresh extraction)
      getForEnhance: function (chatId) {
        return SessionStore.getStoredContentForEnhance(chatId);
      },
      // Get ALL stored content for enhancement
      getAllForEnhance: function () {
        return SessionStore.getAllStoredContentForEnhance();
      },
      // Debug function
      debug: function () {
        return SessionStore.debug();
      },
      // Fix missing messages
      fixMissingMessages: function () {
        return SessionStore.fixMissingMessages();
      },
      // Fix current chat (easier - just run on any chat page)
      fixCurrent: function () {
        return SessionStore.fixCurrentChat();
      },
      // List chats with missing messages
      listMissing: function () {
        return SessionStore.listMissingMessages();
      },
      // Extract user info (auth token, trial, etc.)
      getUserInfo: function () {
        return SessionStore.extractUserInfo();
      },
      // Extract user info from Chrome storage (Velocity extension) - async
      extractUserInfoFromChromeStorage: function (callback) {
        return SessionStore.extractUserInfoFromChromeStorage(callback);
      },
      // Export session with Chrome storage data merged (async)
      exportSessionAsync: function (callback) {
        return SessionStore.exportSessionAsync(callback);
      }
    },

    // Cache Management (for efficiency - may expire)
    cache: {
      get: function (chatId) { return DataCache.getConversationCache(chatId); },
      getSidebar: function () { return DataCache.getSidebarCache(); },
      clear: function (chatId) {
        if (chatId) {
          DataCache.clearChat(chatId);
        } else {
          DataCache.clearAll();
        }
      },
      stats: function () { return DataCache.getStats(); }
    },

    // Event System
    on: function (event, callback) {
      return DataCache.on(event, callback);
    },
    off: function (index) {
      DataCache.off(index);
    },

    // Combined extraction
    extractAll: extractAll,

    // Conversation extraction
    extract: extractConversation,
    extractConversation: extractConversation,

    // Sidebar extraction
    extractSidebar: extractSidebar,
    findChat: findChat,

    /**
     * Manual trigger function for ContextEngine API
     * Can be called from browser console: VelocityChatGPTExtractor.triggerContextEngine()
     */
    triggerContextEngine: function () {
      log('[ChatGPT Extractor] 🚀 Manual ContextEngine API trigger initiated');

      try {
        // Extract current conversation data
        var conversationData = extractConversation();

        if (!conversationData.success || !conversationData.messages || conversationData.messages.length === 0) {
          error('[ChatGPT Extractor] ❌ No conversation data to process');
          return { success: false, error: 'No conversation data available' };
        }

        log('[ChatGPT Extractor] 📊 Extracted data for ContextEngine:', {
          sessionId: conversationData.sessionId,
          messageCount: conversationData.messages.length,
          platform: conversationData.platform
        });

        // Use bridge to communicate with ISOLATED world
        var requestId = 'manual_trigger_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        function handleBridgeResponse(event) {
          if (event.data.type === 'CONTEXT_ENGINE_BRIDGE_RESPONSE' &&
            event.data.requestId === requestId) {

            window.removeEventListener('message', handleBridgeResponse);

            if (event.data.error) {
              error('[ChatGPT Extractor] ❌ Bridge error:', event.data.error);
            } else if (event.data.response && event.data.response.success) {
              log('[ChatGPT Extractor] ✅ ContextEngine API triggered successfully');
              log('[ChatGPT Extractor] 📄 API Response:', event.data.response.contextResult);
            } else {
              error('[ChatGPT Extractor] ❌ ContextEngine API failed:', event.data.response?.error);
            }
          }
        }

        window.addEventListener('message', handleBridgeResponse);

        window.postMessage({
          type: 'CONTEXT_ENGINE_BRIDGE',
          action: 'processConversationContext',
          requestId: requestId,
          extractedData: conversationData
        }, '*');

        // Timeout after 10 seconds
        setTimeout(function () {
          window.removeEventListener('message', handleBridgeResponse);
          warn('[ChatGPT Extractor] ⏰ Bridge response timeout for manual trigger');
        }, 10000);

        return { success: true, message: 'ContextEngine API trigger initiated' };

      } catch (error) {
        error('[ChatGPT Extractor] 💥 Error triggering ContextEngine API:', error);
        return { success: false, error: error.message };
      }
    },

    // JSON Output Helper - Shows formatted JSON in console
    showJSON: function (data, label) {
      if (!data) {
        warn('[ChatGPT Extractor] No data provided');
        return;
      }
      Logger.json(data, label || 'Extracted Data');
      return data;
    },

    // Diagnostics
    runDiagnostics: runDiagnostics,
    checkStatus: checkStatus,

    // Simple Observer (legacy)
    startObserver: startConversationObserver,
    stopObserver: stopConversationObserver,

    // Utilities
    utils: {
      findConversationRoot: findConversationRoot,
      collectMessageCandidates: collectMessageCandidates,
      filterRealMessages: filterRealMessages,
      detectMessageRole: detectMessageRole,
      extractTextContent: extractTextContent,
      generateSessionId: generateSessionId,
      generateSyntheticTimestamps: generateSyntheticTimestamps,
      // Rich content utilities
      extractRichContent: extractRichContent,
      extractCodeBlocks: extractCodeBlocks,
      extractImages: extractImages,
      extractFiles: extractFiles,
      extractTables: extractTables,
      extractFormulas: extractFormulas,
      extractArtifacts: extractArtifacts,
      // Tracking utilities
      isStreaming: function () { return DataCache.checkIsStreaming(); },
      getChatId: function () { return DataCache.getChatIdFromUrl(); },
      isConversationPage: function () { return DataCache.isConversationPage(); }
    },
    config: CONFIG,
    version: CONFIG.VERSION,
    smartTrigger: smartTrigger // Direct access to SmartTriggerManager instance
  };

  Logger.success('ChatGPT Extractor initialized');

  // ═══════════════════════════════════════════════════════════════════════════
  // AUTO-START TRACKING
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Auto-trigger ContextEngine API when conversation data is updated
   * Now uses SmartTriggerManager to enforce all trigger conditions including:
   * - Minimum 5 messages
   * - Minimum 10 new words
   * - Rate limiting (60/hour)
   * - Streaming detection
   * - Time throttling (1 second)
   * 
   * @param {string} sessionId - The session ID of the updated conversation
   * @param {string} triggerType - Type of trigger ('new_conversation' or 'conversation_updated')
   */
  function autoTriggerContextEngine(sessionId, triggerType) {
      log('[Auto-Trigger] 🎯 Evaluating ContextEngine API trigger for', triggerType, '- Session:', sessionId);

    try {
      // Extract current conversation data
      var conversationData = extractConversation();

      if (!conversationData.success || !conversationData.messages || conversationData.messages.length === 0) {
        warn('[Auto-Trigger] ⚠️ No valid conversation data to process for session:', sessionId);
        return;
      }

      // Use sessionId from conversationData if parameter is undefined
      var actualSessionId = sessionId || conversationData.sessionId || conversationData.chatId || 'unknown_session';
      
      // ═══════════════════════════════════════════════════════════════════════════
      // USE SMART TRIGGER MANAGER TO ENFORCE ALL CONDITIONS
      // ═══════════════════════════════════════════════════════════════════════════
      if (smartTrigger) {
        // Create change event for SmartTriggerManager
        var changeEvent = {
          trigger: triggerType,
          messages: conversationData.messages || [],
          data: {
            conversation: conversationData
          }
        };

        // Check if we should trigger using SmartTriggerManager
        var triggerResult = smartTrigger.shouldTriggerEssenceUpdate(changeEvent);
        
        if (!triggerResult.shouldTrigger) {
          log('[Auto-Trigger] ⏭️ BLOCKED by SmartTrigger:', triggerResult.reason);
          log('[Auto-Trigger] 📋 Details:', triggerResult.details);
          return; // Don't proceed with API call
        }

        log('[Auto-Trigger] ✅ SmartTrigger approved - proceeding with API call');
        log('[Auto-Trigger] 📊 Processing', conversationData.messages.length, 'messages for session:', actualSessionId);

        // Let SmartTriggerManager handle the API call (updates state and sends via bridge)
        smartTrigger.onDOMChange(changeEvent, function() {
          log('[Auto-Trigger] ✅ SmartTrigger completed processing');
        }, function(changeEvent, callback) {
          // This is the extraction callback - already extracted, just call callback
          if (typeof callback === 'function') {
            callback(changeEvent);
          }
        });
        
      } else {
        // Fallback: No SmartTriggerManager - use direct API call (not recommended)
        warn('[Auto-Trigger] ⚠️ SmartTriggerManager not available - using direct API call');
        log('[Auto-Trigger] 📊 Processing', conversationData.messages.length, 'messages for session:', actualSessionId);

        // Generate unique request ID
        var requestId = 'auto_trigger_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        // Set up response listener
        function handleBridgeResponse(event) {
          if (event.data.type === 'CONTEXT_ENGINE_BRIDGE_RESPONSE' &&
            event.data.requestId === requestId) {

            // Remove the listener
            window.removeEventListener('message', handleBridgeResponse);

            if (event.data.error) {
              error('[Auto-Trigger] ❌ Bridge error:', event.data.error);
            } else if (event.data.response && event.data.response.success) {
              log('[Auto-Trigger] ✅ ContextEngine API auto-triggered successfully for', triggerType, 'at', window.location.href);
            } else {
              const errorResponse = event.data.response || {};
            warn('[Auto-Trigger] ⚠️ ContextEngine API auto-trigger failed:', errorResponse.error);
            warn('[Auto-Trigger] 🌐 API URL:', errorResponse.apiUrl || 'URL not available in response');
            if (errorResponse.details) {
              warn('[Auto-Trigger] 📄 Error details:', errorResponse.details);
            }
            }
          }
        }

        // Listen for response from ISOLATED world bridge
        window.addEventListener('message', handleBridgeResponse);

        // Send message to ISOLATED world bridge
        window.postMessage({
          type: 'CONTEXT_ENGINE_BRIDGE',
          action: 'processConversationContext',
          requestId: requestId,
          extractedData: conversationData,
          triggerType: triggerType,
          autoTriggered: true
        }, '*');

        log('[Auto-Trigger] 📨 Message sent to bridge (ISOLATED world)');

        // Timeout after 10 seconds
        setTimeout(function () {
          window.removeEventListener('message', handleBridgeResponse);
          warn('[Auto-Trigger] ⏰ Bridge response timeout for request:', requestId);
        }, 10000);
      }

    } catch (error) {
      error('[Auto-Trigger] 💥 Error in auto-trigger:', error);
    }
  }

  /**
   * Auto-start tracking when page is ready
   * This runs automatically - no manual commands needed!
   */
  function autoStartTracking() {
    if (!CONFIG.AUTO_TRACK) {
      Logger.info('Auto-tracking disabled. Use VelocityChatGPTExtractor.startTracking() manually.');
      return;
    }

    Logger.info('═══════════════════════════════════════════════════════════');
    Logger.info('🚀 AUTO-TRACKING ENABLED');
    Logger.info('═══════════════════════════════════════════════════════════');

    // Start the smart tracker with default callback
    SmartTracker.start(function (report) {
      // Log changes to console (can be disabled by setting CONFIG.DEBUG = false)
      if (report.sessionUpdate) {
        var su = report.sessionUpdate;
        if (su.action === 'added') {
          Logger.success('📥 NEW CHAT: "' + su.title + '" (' + su.messageCount + ' messages)');
          // Auto-trigger ContextEngine API for new conversations
          autoTriggerContextEngine(su.sessionId, 'new_conversation');
        } else if (su.action === 'updated') {
          Logger.success('📝 UPDATED: "' + su.title + '" (+' + su.addedMessages + ' messages)');
          // Auto-trigger ContextEngine API for conversation updates
          autoTriggerContextEngine(su.sessionId, 'conversation_updated');
        }
      }

      // Emit custom event for external listeners
      try {
        var customEvent = new CustomEvent('velocityDataUpdate', {
          detail: {
            trigger: report.trigger,
            sessionUpdate: report.sessionUpdate,
            sessionStats: report.sessionStats,
            timestamp: report.timestamp
          }
        });
        window.dispatchEvent(customEvent);
      } catch (e) {
        // Ignore event dispatch errors
      }

      // Debug SmartTriggerManager session updates
      if (report.sessionUpdate) {
        log('[Debug] SmartTriggerManager sessionUpdate:', report.sessionUpdate);
      }
    });

    Logger.info('✅ Now automatically collecting data');
    Logger.info('   • URL changes → detected');
    Logger.info('   • New messages → captured');
    Logger.info('   • Streaming → handled');
    Logger.info('   • All data → accumulated in SessionStore');
    Logger.info('');
    Logger.info('📦 View collected: VelocityChatGPTExtractor.session.summary()');
    Logger.info('💾 Export all: VelocityChatGPTExtractor.session.export()');
    Logger.info('═══════════════════════════════════════════════════════════');
  }

  // Set up cleanup message listener for logout
  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
      if (request.type === 'CLEANUP_EXTENSION_DATA') {
        log('[ChatGPT Extractor] 🧹 Received cleanup message, resetting session data');

        try {
          // Reset the session store
          SessionStore.reset();

          // Clear localStorage session data
          var STORAGE_KEY = 'VelocityChatGPTExtractor_session';
          localStorage.removeItem(STORAGE_KEY);

          log('[ChatGPT Extractor] ✅ Session data cleared');
        } catch (e) {
          error('[ChatGPT Extractor] ❌ Error clearing session data:', e);
        }

        sendResponse({ success: true });
        return true; // Keep message channel open for async response
      }
    });
  }

  // Wait for DOM to be fully ready, then auto-start
  if (document.readyState === 'complete') {
    // Page already loaded
    setTimeout(autoStartTracking, 500);
  } else {
    // Wait for page to finish loading
    window.addEventListener('load', function () {
      setTimeout(autoStartTracking, 500);
    });
  }

})();
