// vydra_frontend/app/contexts/AdProvider.tsx

"use client"; // This is a client-side provider

import React, { 
  createContext, 
  useContext, 
  useState, 
  useEffect, 
  useCallback 
} from 'react';
import Script from 'next/script';

// --- REFACTOR: Replace these with your real IDs ---
// You get this from your AdSense "Rewarded Ad" unit
const REWARDED_AD_UNIT_ID = "ca-pub-3510699448181207/1234567890"; // <-- REPLACE THIS
const AD_CLIENT_ID = "ca-pub-3510699448181207"; // Your publisher ID

// Define TypeScript types for the Google Ad objects we use
type RewardedAd = {
  show: (options?: {
    onUserEarnedReward?: () => void;
    onAdClosed?: () => void;
  }) => void;
};

interface GoogleAdPlatform {
  requestRewardedAd: (options: {
    adUnitId: string;
    onAdLoaded?: (ad: RewardedAd) => void;
    onAdFailedToLoad?: (error: unknown) => void;
  }) => void;
}

// Extend the Window interface with the concrete shape (optional)
declare global {
  interface Window {
    google_ad_platform?: GoogleAdPlatform;
  }
}

// Define what our context will provide
interface AdContextType {
  showRewardedAd: (onReward: () => void) => void;
  isAdReady: boolean;
}

// Create the context
const AdContext = createContext<AdContextType | null>(null);

/**
 * This is the "Provider" component. It will wrap our whole app.
 * Its job is to load the ad SDK and pre-load a rewarded ad.
 */
export const AdProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [rewardedAd, setRewardedAd] = useState<RewardedAd | null>(null); // State to hold the ad
  const [isAdReady, setIsAdReady] = useState(false); // Is the ad loaded?

  // This function pre-loads a new rewarded ad
  const preloadAd = useCallback(() => {
    setIsAdReady(false);
    if (window.google_ad_platform) {
      console.log("Pre-loading new rewarded ad...");
      window.google_ad_platform.requestRewardedAd({
        adUnitId: REWARDED_AD_UNIT_ID,
        onAdLoaded: (ad: RewardedAd) => {
          console.log("Rewarded ad loaded successfully.");
          setRewardedAd(ad);
          setIsAdReady(true);
        },
        onAdFailedToLoad: (error: unknown) => {
          console.error("Rewarded ad failed to load:", error);
          setIsAdReady(false);
        },
      });
    }
  }, []);

  // This effect runs once to load the SDK and the first ad
  useEffect(() => {
    if (window.google_ad_platform) {
      // Defer the preload to the next tick to avoid synchronous setState inside the effect
      const id = setTimeout(() => {
        preloadAd();
      }, 0);
      return () => clearTimeout(id);
    }
  }, [preloadAd]);

  /**
   * This is the function our "Unlock" button will call.
   * It shows the ad and runs the 'onReward' function (our download)
   * only if the user successfully watches the ad.
   */
  const showRewardedAd = (onReward: () => void) => {
    if (rewardedAd && isAdReady) {
      console.log("Showing rewarded ad...");
      rewardedAd.show({
        onUserEarnedReward: () => {
          console.log("User earned reward!");
          onReward(); // This is the "magic" - we run the download
          preloadAd(); // Load the next ad
        },
        onAdClosed: () => {
          console.log("Ad closed by user.");
          // We must always load a new ad when one is closed
          preloadAd();
        },
      });
    } else {
      console.error("Ad not ready to be shown.");
      // Fallback: For development, just give the reward
      // onReward(); 
      alert("Ad is not ready yet. Please try again in a moment.");
    }
  };

  return (
    <AdContext.Provider value={{ showRewardedAd, isAdReady }}>
      {/* This is the *new* Google Ad SDK for rewarded ads.
        We load it here.
      */}
      <Script
        src="https://www.googletagservices.com/ads/rewarded/api/v1/rewarded_ads.js"
        onLoad={() => {
          console.log("Rewarded Ad SDK loaded.");
          // Once the script is loaded, preload the ad
          preloadAd();
        }}
      />
      {children}
    </AdContext.Provider>
  );
};

/**
 * This is a "hook". It's a simple way for our page
 * to get access to the 'showRewardedAd' function.
 */
export const useAdContext = () => {
  const context = useContext(AdContext);
  if (!context) {
    throw new Error("useAdContext must be used within an AdProvider");
  }
  return context;
};