import type { Metadata } from "next";
import { Suspense } from "react";
import LiveStatus from "@/components/LiveStatus";
import SideRail from "@/components/SideRail";
import { fontVariableClasses } from "@/styles/fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "Paper Trader Dashboard",
  description: "Signal quality and paper trading performance overview",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={fontVariableClasses}>
      <body>
        <a className="skip-link" href="#content">
          Skip to content
        </a>
        <Suspense fallback={<aside className="rail" />}>
          <SideRail />
        </Suspense>
        <div className="canvas">
          <Suspense fallback={null}>
            <LiveStatus />
          </Suspense>
          {children}
        </div>
      </body>
    </html>
  );
}
