// vydra_frontend/app/page.tsx

"use client"; 

import React, { useState, useEffect } from 'react'; 
import Image from 'next/image'; // IMPORTANT: You need Image import if you use <Image> component
import { AnalyzeResponse, FormatInfo } from './types'; 
import { sanitizeFilename } from './utils';
import AdDisplay from './components/AdDisplay'; 


// --- (Spinner and ErrorMessage components are unchanged) ---
const Spinner = ()=>(<div className="flex justify-center items-center my-6"><div className="animate-spin rounded-full h-16 w-16 border-b-4 border-purple-300"></div><span className="text-white/80 text-lg ml-4">Analyzing link...</span></div>);
const ErrorMessage = ({message}:{message:string})=>(<div className="bg-red-500/20 backdrop-blur-sm border border-red-500 text-red-100 px-5 py-4 rounded-2xl my-6" role="alert"><strong className="font-bold flex items-center gap-2"><i className="fas fa-exclamation-triangle"></i>Error: </strong><span className="block mt-2">{message}</span></div>);


// --- REFACTOR: New "Wait-to-Unlock" Modal ---
const UnlockProModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onUnlock: () => void;
  adSlotId: string;
}> = ({ isOpen, onClose, onUnlock, adSlotId }) => {
  
  const [countdown, setCountdown] = useState(15); 
  const [isAdLoaded, setIsAdLoaded] = useState(false); 

  useEffect(() => {
    if (isOpen) {
      const initTimer = setTimeout(() => {
        setCountdown(15);
      }, 0);

      const interval = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(interval);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      const adLoadTimer = setTimeout(() => {
        setIsAdLoaded(true);
      }, 2000);

      return () => {
        clearTimeout(initTimer);
        clearInterval(interval);
        clearTimeout(adLoadTimer);
        setIsAdLoaded(false);
      };
    }
  }, [isOpen]); 

  if (!isOpen) return null;

  const isUnlockable = (countdown === 0) && isAdLoaded;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-md flex items-center justify-center z-50 p-4">
      <div className="bg-gradient-to-br from-purple-900 to-indigo-900 p-8 rounded-3xl shadow-2xl border border-white/20 max-w-md w-full text-center">
        <h2 className="text-3xl font-black text-white mb-3">Unlock PRO Format</h2>
        <p className="text-white/80 mb-6">
          Please view this ad for 15 seconds to unlock your download.
        </p>
        
        <div className="w-full flex justify-center my-4">
          <div className="w-[300px] min-h-[250px] bg-white/10 flex items-center justify-center">
            <AdDisplay key={adSlotId} slot={adSlotId} format="rectangle" />
          </div>
        </div>
        
        <button
          onClick={onUnlock}
          disabled={!isUnlockable}
          className="w-full bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white px-10 py-4 rounded-xl font-bold transition-all flex items-center justify-center gap-3 shadow-xl hover:shadow-2xl hover:scale-105 text-lg disabled:opacity-50 disabled:cursor-not-allowed pulse-glow"
        >
          <i className={`fas ${!isUnlockable ? 'fa-hourglass-half' : 'fa-check'}`}></i>
          <span>
            {isUnlockable ? 'Unlock & Download' : `Please wait... (${countdown}s)`}
          </span>
        </button>
        
        <button
          onClick={onClose}
          className="w-full text-white/60 hover:text-white transition-all mt-4"
        >
          Cancel
        </button>
      </div>
    </div>
  );
};


// --- Main Page Component ---
export default function Home() {
  
  const [url, setUrl] = useState<string>(""); 
  const [loading, setLoading] = useState<boolean>(false); 
  const [error, setError] = useState<string | null>(null); 
  const [results, setResults] = useState<AnalyzeResponse | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState<FormatInfo | null>(null);

  // --- REFACTOR: Define API_URL once at the component level for consistency ---
  // This is the correct "top-class" way to access environment variables in Next.js
  // for client-side code.
  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const handleFetch = async (e: React.FormEvent) => {
    e.preventDefault(); 
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      // Use the API_URL defined above
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "An unknown error occurred.");
      }
      const data: AnalyzeResponse = await response.json();
      setResults(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message || "Failed to connect to the backend. Is it running?");
      } else if (typeof err === 'string') {
        setError(err);
      } else {
        setError("Failed to connect to the backend. Is it running?");
      }
    } finally {
      setLoading(false);
    }
  };

  const _handleDownload = (format: FormatInfo) => {
    if (!results) return;
    
    console.log(`Triggering download for: ${format.format_id}`);
    const { format_id, ext, quality } = format;
    const { title, original_url } = results;

    const encodedUrl = encodeURIComponent(original_url);
    const encodedFormatId = encodeURIComponent(format_id);
    const encodedTitle = encodeURIComponent(title);
    const encodedExt = encodeURIComponent(ext);
    const encodedQuality = encodeURIComponent(quality);

    // Use the API_URL defined above
    const downloadUrl = `${API_URL}/api/download?url=${encodedUrl}&format_id=${encodedFormatId}&title=${encodedTitle}&ext=${encodedExt}&quality=${encodedQuality}`;

    window.location.href = downloadUrl;
  };

  const handleFormatClick = (format: FormatInfo) => {
    if (format.is_premium) {
      setSelectedFormat(format);
      setIsModalOpen(true);
    } else {
      _handleDownload(format);
    }
  };

  const handleUnlockRequest = () => {
    if (selectedFormat) {
      _handleDownload(selectedFormat);
      setIsModalOpen(false);
      setSelectedFormat(null);
    }
  };

  // --- Rendered UI (JSX) ---
  return (
    <> 
      <main className="container mx-auto px-4 py-8 md:py-12">
        <div className="max-w-6xl mx-auto">
          
          <div className="text-center mb-8 md:mb-12">
            <div className="flex items-center justify-center mb-4 md:mb-6 float-animation">
              {/* Corrected: Using Next.js Image component for the logo */}
              <Image
                src="/vydra-logo.png"
                alt="Vydra Logo"
                width={64}
                height={64}
                className="w-16 h-16 md:w-20 md:h-20"
                priority
              />
            </div>
            <h1 className="text-5xl md:text-7xl font-black text-white mb-3 md:mb-4 tracking-tight">Vydra</h1>
            <p className="text-xl md:text-3xl font-bold bg-gradient-to-r from-purple-300 via-pink-300 to-blue-300 bg-clip-text text-transparent mb-2 md:mb-3">Download everything, anywhere.</p>
            <p className="text-sm md:text-base text-white/70 max-w-2xl mx-auto px-4">Your ultimate video downloader for all platforms. Fast, secure, and completely free.</p>
          </div>
          <div className="bg-white/10 backdrop-blur-xl rounded-3xl shadow-2xl p-6 md:p-10 border border-white/20 mb-8 md:mb-12">
            <form onSubmit={handleFetch}>
              <label className="block text-white font-bold mb-3 md:mb-4 text-sm md:text-base flex items-center gap-2"><i className="fas fa-link text-purple-300"></i>Paste Video URL</label>
              <div className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  className="flex-1 px-4 md:px-6 py-3 md:py-4 bg-white/90 backdrop-blur-sm border-2 border-transparent rounded-xl focus:outline-none focus:border-purple-400 focus:bg-white transition-all text-gray-800 placeholder-gray-400 text-sm md:text-base shadow-lg"
                  required
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white px-6 md:px-10 py-3 md:py-4 rounded-xl font-bold transition-all flex items-center justify-center gap-2 shadow-xl hover:shadow-2xl hover:scale-105 text-sm md:text-base disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <i className={`fas ${loading ? 'fa-spinner animate-spin' : 'fa-search'}`}></i>
                  <span>{loading ? 'Fetching...' : 'Fetch'}</span>
                </button>
              </div>
            </form>
            <div className="mt-8">
              {loading && <Spinner />}
              {error && <ErrorMessage message={error} />}
              {results && (
                <div className="border-t border-white/20 pt-8">
                  <div className="flex flex-col md:flex-row gap-6">
                    {results.thumbnail && (
                      <img 
                        src={results.thumbnail} 
                        alt="Media Thumbnail"
                        className="w-full md:w-1/3 rounded-2xl shadow-lg border border-white/20 object-cover"
                      />
                    )}
                    <div className="flex-1">
                      <h2 className="text-2xl md:text-3xl font-bold text-white mb-5">
                        {results.title}
                      </h2>
                      
                      <label className="block text-white font-bold mb-3 text-sm md:text-base flex items-center gap-2">
                        <i className="fas fa-download text-purple-300"></i>Select a format to download
                      </label>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        
                        {results.formats.map((format, index) => (
                          <button
                            key={index}
                            onClick={() => handleFormatClick(format)}
                            className={`
                              bg-white/10 backdrop-blur-sm border-2 border-white/30 rounded-xl p-4 
                              transition-all flex items-center justify-between gap-3 group
                              ${format.is_premium 
                                ? 'hover:border-yellow-400 hover:bg-white/20' 
                                : 'hover:border-purple-400 hover:bg-white/20'}
                            `}
                          >
                            <div className="flex items-center gap-3">
                              <div className={`
                                p-2 rounded-lg transition-transform
                                ${format.is_premium 
                                  ? 'bg-yellow-500/80 group-hover:scale-110' 
                                  : 'bg-gradient-to-br from-purple-500 to-pink-500 group-hover:scale-110'}
                              `}>
                                <i className={`fas ${
                                  format.is_premium 
                                    ? 'fa-gem' 
                                    : (format.ext.includes('mp3') || format.ext.includes('m4a') ? 'fa-music' : 'fa-video')
                                  } text-white text-lg`}></i>
                              </div>
                              <div className="text-left">
                                <div className="font-bold text-white text-sm md:text-base">{format.quality}</div>
                                <div className="text-xs text-white/60">{format.ext.toUpperCase()}</div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {format.is_premium && (
                                <span className="text-sm bg-yellow-500/30 text-yellow-300 font-bold px-3 py-1 rounded-full">
                                  PRO
                                </span>
                              )}
                              {format.size_mb && (
                                <span className="text-sm bg-gray-900/50 text-white/80 px-3 py-1 rounded-full hidden sm:block">
                                  {format.size_mb} MB
                                </span>
                              )}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
          
          {/* --- (Footer section is unchanged) --- */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6 mb-8 md:mb-12">
            <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-5 md:p-6 border border-white/20 text-center hover:bg-white/15 transition-all"><div className="bg-gradient-to-br from-green-400 to-emerald-500 w-11 h-11 md:w-16 md:h-16 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4 shadow-lg"><i className="fas fa-bolt text-white text-xl md:text-2xl"></i></div><h3 className="text-white font-bold text-base md:text-lg mb-2">Lightning Fast</h3><p className="text-white/70 text-xs md:text-sm">Download videos in seconds with our optimized servers</p></div>
            <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-5 md:p-6 border border-white/20 text-center hover:bg-white/15 transition-all"><div className="bg-gradient-to-br from-blue-400 to-cyan-500 w-11 h-11 md:w-16 md:h-16 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4 shadow-lg"><i className="fas fa-shield-alt text-white text-xl md:text-2xl"></i></div><h3 className="text-white font-bold text-base md:text-lg mb-2">100% Secure</h3><p className="text-white/70 text-xs md:text-sm">Your privacy is protected. No data stored or shared</p></div>
            <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-5 md:p-6 border border-white/20 text-center hover:bg-white/15 transition-all"><div className="bg-gradient-to-br from-purple-400 to-pink-500 w-11 h-11 md:w-16 md:h-16 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4 shadow-lg"><i className="fas fa-infinity text-white text-xl md:text-2xl"></i></div><h3 className="text-white font-bold text-base md:text-lg mb-2">Unlimited Downloads</h3><p className="text-white/70 text-xs md:text-sm">No limits, no restrictions. Download as much as you want</p></div>
          </div>
          <AdDisplay slot="6711810243" /> 
          <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 backdrop-blur-xl rounded-3xl p-6 md:p-10 border border-white/20">
            <h2 className="text-2xl md:text-3xl font-black text-white mb-6 md:mb-8 text-center">Supported Platforms</h2>
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-4 md:gap-6">
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-youtube text-red-600 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">YouTube</span></div>
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-facebook text-blue-600 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">Facebook</span></div>
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-instagram text-pink-600 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">Instagram</span></div>
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-twitter text-blue-400 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">Twitter</span></div>
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-tiktok text-gray-800 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">TikTok</span></div>
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-vimeo text-blue-500 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">Vimeo</span></div>
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-twitch text-purple-600 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">Twitch</span></div>
              <div className="flex flex-col items-center gap-2 md:gap-3 group"><div className="bg-white rounded-2xl w-14 h-14 md:w-20 md:h-20 flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform"><i className="fab fa-dailymotion text-blue-700 text-2xl md:text-3xl"></i></div><span className="text-white text-xs md:text-sm font-bold">Dailymotion</span></div>
            </div>
          </div>
          <div className="mt-8 md:mt-12 text-center"><p className="text-white/60 text-xs md:text-sm mb-4">© 2025 Vydra. All rights reserved.</p><div className="flex items-center justify-center gap-4 md:gap-6"><a href="#" className="text-white/70 hover:text-white transition-colors text-xs md:text-sm">Privacy Policy</a><a href="#" className="text-white/70 hover:text-white transition-colors text-xs md:text-sm">Terms of Service</a><a href="#" className="text-white/70 hover:text-white transition-colors text-xs md:text-sm">Contact</a></div></div>
        </div>
      </main>

      <UnlockProModal
        isOpen={isModalOpen}
        adSlotId="3664465767"
        onClose={() => {
          setIsModalOpen(false);
          setSelectedFormat(null);
        }}
        onUnlock={handleUnlockRequest}
      />
    </>
  );
}