// vydra_frontend/app/components/AdDisplay.tsx

"use client"; // This component MUST be a client component

import React, { useEffect } from 'react';

declare global {
  interface Window {
    // AdSense uses a global array that you push command objects into.
    // Use unknown[] to avoid the 'any' lint rule while still allowing array operations.
    adsbygoogle?: unknown[];
  }
}

interface AdDisplayProps {
  slot: string; // Your ad slot ID
  format?: 'auto' | 'rectangle' | 'vertical' | 'horizontal';
  responsive?: boolean;
}

const AdDisplay: React.FC<AdDisplayProps> = ({
  slot,
  format = 'auto',
  responsive = true,
}) => {
  
  // --- REFACTOR: Your Publisher ID is now here ---
  const AD_CLIENT_ID = "ca-pub-3510699448181207"; // <-- YOUR ID IS IN!

  useEffect(() => {
    try {
      if (window.adsbygoogle) {
        // console.log('Pushing ad to slot:', slot); // Good for debugging
        (window.adsbygoogle = window.adsbygoogle || []).push({});
      }
    } catch (e) {
      console.error('Error pushing AdSense ad:', e);
    }
  }, [slot]); // Re-run if the slot ID changes

  return (
    <div 
      key={slot} 
      className="text-center my-6 min-h-[100px] w-full"
      aria-label="Advertisement"
    >
      <ins
        className="adsbygoogle"
        style={{ display: 'block' }}
        data-ad-client={AD_CLIENT_ID} // <-- YOUR ID
        data-ad-slot={slot} // Your specific ad unit's ID
        data-ad-format={format}
        data-full-width-responsive={responsive.toString()}
      ></ins>
    </div>
  );
};

export default AdDisplay;