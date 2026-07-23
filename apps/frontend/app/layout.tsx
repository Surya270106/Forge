import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

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
      <body className={inter.className}>
        <div className="flex h-screen w-full flex-col md:flex-row overflow-hidden bg-background">
          {/* Minimal App Shell Sidebar */}
          <aside className="w-64 border-r border-border bg-surface p-4 flex flex-col hidden md:flex">
            <div className="font-semibold text-lg mb-8 tracking-tight">Forge</div>
            <nav className="flex flex-col gap-2">
              <a href="#" className="px-3 py-2 bg-accent/10 text-accent rounded-md font-medium text-sm">Dashboard</a>
              <a href="#" className="px-3 py-2 text-muted hover:bg-muted-bg rounded-md font-medium text-sm transition-colors">Repositories</a>
              <a href="#" className="px-3 py-2 text-muted hover:bg-muted-bg rounded-md font-medium text-sm transition-colors">Runs</a>
            </nav>
          </aside>
          
          <main className="flex-1 flex flex-col h-full relative overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
