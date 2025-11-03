// vydra_frontend/app/utils.ts

// This file holds helper functions used across the app.

/**
 * Sanitizes a string to be a valid filename.
 * (This is the JavaScript version of the logic in your `Working.py`)
 * @param name The string to sanitize
 * @returns A safe filename string
 */
export function sanitizeFilename(name: string): string {
  if (!name) return "untitled";
  
  // Replace illegal characters with an empty string
  let sanitized = name.replace(/[<>:"/\\|?*\x00-\x1F]/g, '');
  
  // Replace multiple spaces/whitespace with a single space
  sanitized = sanitized.replace(/\s+/g, ' ').trim();

  // Limit length to avoid OS issues (e.g., 200 chars)
  if (sanitized.length > 200) {
    sanitized = sanitized.substring(0, 200).trim();
  }

  // If all characters were illegal, provide a default
  if (!sanitized) return "download";

  return sanitized;
}