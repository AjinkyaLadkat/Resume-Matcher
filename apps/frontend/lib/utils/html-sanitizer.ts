// import DOMPurify from 'dompurify';

// const purify = typeof window !== 'undefined' ? DOMPurify(window) : null;

// /**
//  * Whitelist of allowed HTML tags for rich text content
//  */
// const ALLOWED_TAGS = ['strong', 'em', 'u', 'a'];

// /**
//  * Whitelist of allowed HTML attributes
//  */
// const ALLOWED_ATTR = ['href', 'target', 'rel'];

// /**
//  * Sanitizes HTML content using DOMPurify with a strict whitelist.
//  * Only allows bold, italic, underline, and link formatting.
//  * Uses isomorphic-dompurify which works in both browser and Node.js.
//  *
//  * @param dirty - The unsanitized HTML string
//  * @returns Sanitized HTML string safe for rendering
//  */
// export function sanitizeHtml(dirty: string): string {
//   return DOMPurify.sanitize(dirty, {
//     ALLOWED_TAGS,
//     ALLOWED_ATTR,
//     FORCE_BODY: true,
//   });
// }

import createDOMPurify from 'dompurify';

const DOMPurify = typeof window !== 'undefined' ? createDOMPurify(window) : null;

const ALLOWED_TAGS = ['b', 'i', 'em', 'strong', 'p', 'ul', 'ol', 'li', 'br', 'span'];

const ALLOWED_ATTR = ['class', 'style'];

export function sanitizeHtml(dirty: string): string {
  if (!DOMPurify) {
    return dirty;
  }

  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    FORCE_BODY: true,
  });
}
