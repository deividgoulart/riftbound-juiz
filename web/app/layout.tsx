import type { Metadata, Viewport } from "next";
import { Cinzel, Inter } from "next/font/google";
import { BarraDeBaixo, Topo } from "@/components/navegacao";
import { JanelaDaSenha } from "@/components/entrar";
import { ProvedorDaSessao } from "@/lib/sessao";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const cinzel = Cinzel({ variable: "--font-cinzel", subsets: ["latin"], weight: ["700"] });

export const metadata: Metadata = {
  title: { default: "Juiz Riftbound", template: "%s · Juiz Riftbound" },
  description: "Tira dúvidas de regras do Riftbound TCG em português e mostra quanto falta pra montar cada deck.",
};

export const viewport: Viewport = { themeColor: "#0a0e18", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className={`${inter.variable} ${cinzel.variable} antialiased`}>
      <body className="min-h-dvh font-sans">
        <ProvedorDaSessao>
          <Topo />
          <main className="mx-auto w-full max-w-5xl px-4 pb-28 pt-5 md:pb-12">{children}</main>
          <BarraDeBaixo />
          <JanelaDaSenha />
        </ProvedorDaSessao>
      </body>
    </html>
  );
}
