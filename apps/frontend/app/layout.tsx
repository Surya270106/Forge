import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import "./globals.css";
import BlobScene from "./components/blob-scene";

const inter = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const robotoMono = Roboto_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Forge AI Workspace",
  description: "Autonomous software engineering platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${robotoMono.variable} antialiased`}>
        <div className="forge-app relative min-h-screen">
          <BlobScene />
          <div className="relative z-10 flex min-h-screen w-full flex-col">
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
