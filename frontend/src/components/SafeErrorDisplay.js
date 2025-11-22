import { ensureString } from '../utils/apiError';

/**
 * Safe error display component that ensures errors are always rendered as strings
 * Prevents "Objects are not valid as a React child" errors
 */
export default function SafeErrorDisplay({ error, className = "" }) {
  if (!error) return null;
  
  const safeError = ensureString(error);
  
  return (
    <div className={className}>
      {safeError}
    </div>
  );
}


