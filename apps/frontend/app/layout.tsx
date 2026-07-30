import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import "./globals.css";
import "../../../forge-antigravity-ui-overhaul-v2/reference-ui/app/globals.css";
import "./workspace.css";
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
  title: "Forge — Intent to verified change",
  description: "Plan, execute, and verify repository changes with Forge.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${robotoMono.variable} antialiased`}>
        <div className="forge-app">
          <BlobScene />
          {children}
        </div>
      </body>
    </html>
  );
}
