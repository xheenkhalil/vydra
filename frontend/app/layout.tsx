// vydra_frontend/app/layout.tsx

import React from 'react';
import Script from 'next/script';
import './globals.css';
// --- REFACTOR: REMOVED AdProvider ---

export const metadata = {
  title: 'Vydra - All Video Downloader',
  description: 'Download everything, anywhere.',
};

const AD_CLIENT_ID = "ca-pub-3510699448181207"; // Your publisher ID

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link
          rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
        />
        {/* This is our AdSense BANNER script (still needed) */}
        <Script
          async
          src={`https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${AD_CLIENT_ID}`}
          crossOrigin="anonymous"
          strategy="afterInteractive"
        />
        {/* --- REFACTOR: REMOVED the rewarded_ads.js script --- */}
      </head>
      <body className="bg-gradient-to-br from-indigo-900 via-purple-900 to-pink-800 min-h-screen relative overflow-x-hidden">
        
        {/* --- REFACTOR: REMOVED the AdProvider wrapper --- */}
        <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1557683316-973673baf926?w=1920')] opacity-5 bg-cover bg-center"></div>
        <div className="absolute inset-0 backdrop-blur-3xl"></div>
        <div className="relative z-10">
          {children}
        </div>

      </body>
    </html>
  );
}