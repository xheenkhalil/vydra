// vydra_frontend/app/types.ts

// REFACTOR: This now matches our new backend model
export interface FormatInfo {
  quality: string;      // The display name, e.g., "Premium HD (1440p)"
  ext: string;
  size_mb: number | null;
  is_premium: boolean;  // True if this is a locked format
  format_id: string;    // The real ID to pass to the proxy
}

export interface AnalyzeResponse {
  title: string;
  thumbnail: string | null;
  formats: FormatInfo[];
  original_url: string; 
}