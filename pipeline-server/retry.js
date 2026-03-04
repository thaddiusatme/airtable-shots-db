/**
 * Retry utility with exponential backoff and error classification.
 * Used by the pipeline orchestrator to handle transient capture failures.
 */

// Patterns that indicate transient (retryable) errors
const TRANSIENT_PATTERNS = [
  /Timeout \d+ms exceeded/i,
  /net::ERR_NETWORK_CHANGED/i,
  /net::ERR_INTERNET_DISCONNECTED/i,
  /net::ERR_CONNECTION_REFUSED/i,
  /net::ERR_CONNECTION_RESET/i,
  /net::ERR_NAME_NOT_RESOLVED/i,
  /Target closed/i,
  /browser has been closed/i,
  /Navigation failed because page was closed/i,
  /Protocol error.*Target closed/i,
  /ECONNREFUSED/i,
  /ECONNRESET/i,
  /ETIMEDOUT/i,
];

// Patterns that indicate permanent (non-retryable) errors
const PERMANENT_PATTERNS = [
  /Invalid YouTube URL/i,
  /could not extract video ID/i,
  /exceeds video duration/i,
  /AIRTABLE_API_KEY/i,
  /AIRTABLE_BASE_ID/i,
  /YT_FRAME_POC_PATH.*not set/i,
  /not found at:/i,
];

/**
 * Check if an error is transient (retryable).
 * Checks both err.message and err.stderr for transient patterns.
 */
function isTransientError(err) {
  const sources = [err.message || '', err.stderr || ''];
  const text = sources.join(' ');
  return TRANSIENT_PATTERNS.some(pattern => pattern.test(text));
}

/**
 * Classify an error as 'transient', 'permanent', or 'unknown'.
 */
function classifyError(err) {
  const sources = [err.message || '', err.stderr || ''];
  const text = sources.join(' ');

  if (PERMANENT_PATTERNS.some(p => p.test(text))) return 'permanent';
  if (TRANSIENT_PATTERNS.some(p => p.test(text))) return 'transient';
  return 'unknown';
}

/**
 * Retry an async function with exponential backoff.
 * Only retries on transient errors; permanent errors are thrown immediately.
 *
 * @param {Function} fn - Async function to execute
 * @param {Object} options
 * @param {number} options.maxRetries - Maximum number of retries (default: 2)
 * @param {number} options.baseDelayMs - Base delay in ms (default: 5000)
 * @param {number} options.maxDelayMs - Maximum delay cap in ms (default: 30000)
 * @param {Function} [options.onRetry] - Callback(attempt, err, delayMs) called before each retry
 * @returns {Promise<*>} Result of fn()
 */
async function retryWithBackoff(fn, options = {}) {
  const {
    maxRetries = 2,
    baseDelayMs = 5000,
    maxDelayMs = 30000,
    onRetry,
  } = options;

  let lastError;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;

      // Don't retry permanent errors
      if (!isTransientError(err)) {
        throw err;
      }

      // Don't retry if we've exhausted all attempts
      if (attempt >= maxRetries) {
        throw err;
      }

      // Calculate delay with exponential backoff
      const delay = Math.min(baseDelayMs * Math.pow(2, attempt), maxDelayMs);

      if (onRetry) {
        onRetry(attempt + 1, err, delay);
      }

      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}

module.exports = {
  isTransientError,
  classifyError,
  retryWithBackoff,
  TRANSIENT_PATTERNS,
  PERMANENT_PATTERNS,
};
