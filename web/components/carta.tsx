"use client";

// A arte da carta e a ficha que abre ao tocar nela: imagem grande, texto oficial, explicação com
// exemplos (escrita de antemão por um LLM local; veja api/gerar_explicacoes.py) e as dúvidas do FAQ.

import Link from "next/link";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import useSWR from "swr";
import { BookOpen, ExternalLink, HelpCircle, MessageCircleQuestion, X } from "lucide-react";
import { buscar, type ExplicacaoDaCarta, type FichaDaCarta } from "@/lib/api";
import { Markdown } from "./markdown";
import { Aviso, NOMES_DOS_DOMINIOS, PontosDosDominios, corDoDominio, juntar } from "./ui";

/** Imagem deitada (os battlefields vêm na horizontal)? Decide pela própria imagem, quando ela carrega. */
function useDeitada(): [boolean, (e: React.SyntheticEvent<HTMLImageElement>) => void] {
  const [deitada, setDeitada] = useState(false);
  return [deitada, (e) => setDeitada(e.currentTarget.naturalWidth > e.currentTarget.naturalHeight)];
}

/** Arte da carta (galeria oficial). Sem imagem, um cartão com as cores dos domínios e o nome.
    Battlefields (imagem na horizontal) são girados pra caber no espaço de uma carta em pé. Com
    `ampliavel`, passar o mouse destaca a carta e clicar (ou tocar, no celular) abre a ficha dela.
    `carta` é o nome no catálogo, quando o nome mostrado é outro ("Jinx, Loose Cannon" x "Loose Cannon"). */
export function ImagemDaCarta({
  nome,
  carta,
  imagem,
  dominios = [],
  className = "",
  ampliavel = true,
}: {
  nome: string;
  carta?: string;
  imagem: string | null | undefined;
  dominios?: string[];
  className?: string;
  ampliavel?: boolean;
}) {
  const [deitada, aoCarregar] = useDeitada();
  const [aberta, setAberta] = useState(false);
  const [a, b] = [corDoDominio(dominios[0]), corDoDominio(dominios[1] ?? dominios[0])];
  return (
    <>
      <div
        role={ampliavel ? "button" : undefined}
        tabIndex={ampliavel ? 0 : undefined}
        aria-label={ampliavel ? `Abrir a ficha de ${nome}` : undefined}
        onClick={ampliavel ? () => setAberta(true) : undefined}
        onKeyDown={ampliavel ? (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setAberta(true)) : undefined}
        className={juntar(
          "relative aspect-[744/1039] overflow-hidden rounded-lg border border-linha bg-superficie-2",
          ampliavel &&
            "cursor-pointer transition duration-200 hover:z-10 hover:-translate-y-0.5 hover:scale-[1.04] hover:border-ouro/70 hover:shadow-xl hover:shadow-black/50 focus-visible:outline-2 focus-visible:outline-ouro",
          className,
        )}
        style={
          imagem
            ? undefined
            : {
                background: `linear-gradient(160deg, color-mix(in srgb, ${a} 45%, transparent), var(--color-superficie-2) 55%, color-mix(in srgb, ${b} 35%, transparent))`,
              }
        }
      >
        {imagem ? (
          // eslint-disable-next-line @next/next/no-img-element -- imagens do site da Riot, sem otimização da Vercel
          <img
            src={imagem}
            alt={nome}
            loading="lazy"
            onLoad={aoCarregar}
            className={
              deitada
                ? // girada 90°: a largura dela vira a altura do quadro, e a altura, a largura
                  "absolute left-1/2 top-1/2 h-[71.6%] w-[139.65%] max-w-none -translate-x-1/2 -translate-y-1/2 rotate-90 object-cover"
                : "h-full w-full object-cover"
            }
          />
        ) : (
          <div className="flex h-full items-end p-2">
            <span className="line-clamp-3 text-[11px] font-semibold leading-tight text-texto/90">{nome}</span>
          </div>
        )}
      </div>
      {aberta && <FichaDaCarta carta={carta ?? nome} imagem={imagem} onFechar={() => setAberta(false)} />}
    </>
  );
}

/** O nome de uma carta como botão que abre a ficha (nas listas sem imagem). */
export function NomeDaCarta({ carta, className = "" }: { carta: string; className?: string }) {
  const [aberta, setAberta] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setAberta(true)} className={juntar("truncate text-left hover:text-ouro hover:underline", className)}>
        {carta}
      </button>
      {aberta && <FichaDaCarta carta={carta} onFechar={() => setAberta(false)} />}
    </>
  );
}

/** Texto da carta com as palavras-chave ([Ambush], [Fury]) em destaque e o lembrete entre parênteses mais apagado. */
function TextoDaCarta({ texto }: { texto: string }) {
  return (
    <div className="space-y-2 text-[15px] leading-relaxed">
      {texto.split("\n").map((linha, i) => (
        <p key={i}>
          {linha.split(/(\[[^\]]+\]|\([^)]*\))/).map((parte, j) => {
            if (/^\[[^\]]+\]$/.test(parte)) {
              const palavra = parte.slice(1, -1);
              const dominio = NOMES_DOS_DOMINIOS[palavra] ? palavra : null;
              return (
                <span
                  key={j}
                  className="mx-0.5 inline-block rounded-md border px-1.5 py-px text-[13px] font-semibold"
                  style={dominio ? { color: corDoDominio(dominio), borderColor: corDoDominio(dominio) } : { color: "var(--color-ouro)", borderColor: "rgb(212 175 90 / 0.45)" }}
                >
                  {palavra}
                </span>
              );
            }
            if (/^\(.*\)$/.test(parte)) return <span key={j} className="italic text-apagado">{parte}</span>;
            return <span key={j}>{parte}</span>;
          })}
        </p>
      ))}
    </div>
  );
}

function Atributos({ ficha }: { ficha: FichaDaCarta }) {
  const { tipos = [], dominios = [], energia, poder, might } = ficha.atributos;
  const itens = [
    tipos.join(" "),
    energia !== null && energia !== undefined ? `Energia ${energia}` : null,
    poder !== null && poder !== undefined ? `Poder ${poder}` : null,
    might !== null && might !== undefined ? `Might ${might}` : null,
  ].filter(Boolean);
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-apagado">
      <PontosDosDominios dominios={dominios} />
      {itens.map((item) => (
        <span key={item} className="rounded-full border border-linha px-2 py-0.5">
          {item}
        </span>
      ))}
    </div>
  );
}

function Explicacao({ explicacao }: { explicacao: ExplicacaoDaCarta }) {
  return (
    <div className="space-y-3">
      <Markdown texto={explicacao.html} />
      <p className="text-xs text-apagado">
        Escrito por um modelo de IA a partir do texto da carta e do FAQ, e conferido só automaticamente. Pode errar: na dúvida, vale a fonte.
      </p>
      {explicacao.fontes.length > 0 && (
        <ul className="space-y-1 border-t border-linha pt-3 text-xs text-apagado">
          {explicacao.fontes.map((f) => (
            <li key={f.numero}>
              <span className="font-semibold text-azul">F{f.numero}</span> ·{" "}
              {f.url ? (
                <a href={f.url} target="_blank" rel="noopener noreferrer" className="underline decoration-linha underline-offset-2 hover:text-texto">
                  {f.titulo}
                </a>
              ) : (
                f.titulo
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A ficha: em tela cheia no celular (rola pra baixo) e em duas colunas no computador. */
export function FichaDaCarta({ carta, imagem, onFechar }: { carta: string; imagem?: string | null; onFechar: () => void }) {
  const { data: ficha, error } = useSWR<FichaDaCarta>(`/api/carta?nome=${encodeURIComponent(carta)}`, buscar, {
    revalidateOnFocus: false,
  });
  const [ampliada, setAmpliada] = useState(false);
  const [deitada, aoCarregar] = useDeitada();
  const arte = ficha?.imagem ?? imagem;

  useEffect(() => {
    const fechar = (e: KeyboardEvent) => e.key === "Escape" && onFechar();
    window.addEventListener("keydown", fechar);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", fechar);
      document.body.style.overflow = "";
    };
  }, [onFechar]);

  return createPortal(
    <div role="dialog" aria-modal aria-label={carta} className="fixed inset-0 z-[60] overflow-y-auto bg-fundo/95 backdrop-blur-sm">
      <button
        type="button"
        onClick={onFechar}
        aria-label="Fechar"
        className="fixed right-4 top-4 z-10 rounded-full border border-linha bg-superficie/90 p-2 text-texto shadow-lg"
      >
        <X size={22} />
      </button>

      {ampliada && arte && (
        // Só a arte, o maior possível; toque fecha
        <button type="button" onClick={() => setAmpliada(false)} className="fixed inset-0 z-20 flex cursor-zoom-out items-center justify-center bg-black/90 p-3">
          {/* eslint-disable-next-line @next/next/no-img-element -- imagens do site da Riot */}
          <img src={arte} alt={carta} className="max-h-full max-w-full rounded-2xl object-contain" />
        </button>
      )}

      <div className="mx-auto grid max-w-5xl gap-6 px-4 pb-16 pt-16 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:pt-12">
        <div className="md:sticky md:top-12 md:self-start">
          {arte ? (
            <button type="button" onClick={() => setAmpliada(true)} className="mx-auto block cursor-zoom-in" aria-label="Ver a arte em tela cheia">
              {/* eslint-disable-next-line @next/next/no-img-element -- imagens do site da Riot */}
              <img
                src={arte}
                alt={carta}
                onLoad={aoCarregar}
                className={juntar("mx-auto rounded-2xl object-contain shadow-2xl shadow-black", deitada ? "max-h-[40dvh] w-full" : "max-h-[55dvh]")}
              />
            </button>
          ) : (
            <ImagemDaCarta nome={carta} imagem={null} dominios={ficha?.atributos.dominios} ampliavel={false} className="mx-auto w-48" />
          )}
        </div>

        <div className="min-w-0 space-y-5">
          <div className="space-y-2">
            <h2 className="font-titulo text-2xl font-bold leading-tight text-ouro">{carta}</h2>
            {ficha && <Atributos ficha={ficha} />}
          </div>

          {error && <Aviso tipo="erro">{error.message}</Aviso>}
          {!ficha && !error && (
            <div className="flex items-center gap-3 py-6 text-sm text-apagado">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-ouro border-t-transparent" /> Carregando a carta...
            </div>
          )}

          {ficha && (
            <>
              {ficha.texto ? (
                <section className="rounded-2xl border border-linha bg-superficie p-4">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-apagado">Texto oficial</h3>
                  <TextoDaCarta texto={ficha.texto} />
                  {ficha.errata && <p className="mt-2 text-xs text-apagado">Esta carta recebeu errata; o texto acima já é o atualizado.</p>}
                </section>
              ) : (
                <p className="text-sm text-apagado">Runa básica: gera a energia e o poder do seu domínio. Não tem texto próprio.</p>
              )}

              {ficha.texto && (
                <section className="rounded-2xl border border-ouro/30 bg-superficie p-4">
                  <h3 className="mb-3 flex items-center gap-2 font-semibold">
                    <BookOpen size={17} className="text-ouro" /> Como usar
                  </h3>
                  {ficha.explicacao ? (
                    <Explicacao explicacao={ficha.explicacao} />
                  ) : (
                    <p className="text-sm text-apagado">
                      A explicação desta carta ainda não foi escrita. Enquanto isso, veja as dúvidas do FAQ abaixo ou pergunte ao juiz.
                    </p>
                  )}
                </section>
              )}

              {(ficha.duvidas.length > 0 || ficha.mecanicas.length > 0) && (
                <section className="rounded-2xl border border-linha bg-superficie p-4">
                  <h3 className="mb-3 flex items-center gap-2 font-semibold">
                    <HelpCircle size={17} className="text-azul" /> Dúvidas e exceções no FAQ
                  </h3>
                  <ul className="space-y-2">
                    {ficha.duvidas.map((d) => (
                      <li key={d.url}>
                        <a href={d.url} target="_blank" rel="noopener noreferrer" className="group flex gap-2 text-sm">
                          <ExternalLink size={14} className="mt-0.5 shrink-0 text-apagado group-hover:text-azul" />
                          <span className="underline decoration-linha underline-offset-2 group-hover:decoration-azul">{d.pergunta}</span>
                        </a>
                      </li>
                    ))}
                  </ul>
                  {ficha.mecanicas.length > 0 && (
                    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-linha pt-3 text-xs text-apagado">
                      Mecânicas:
                      {ficha.mecanicas.map((m) => (
                        <a key={m.url} href={m.url} target="_blank" rel="noopener noreferrer" className="rounded-full border border-linha px-2.5 py-1 text-texto hover:border-azul">
                          {m.pagina}
                        </a>
                      ))}
                    </div>
                  )}
                  <p className="mt-3 text-xs text-apagado">Respostas em inglês, do Riftbound FAQ (não oficial). Em caso de dúvida, vale o Core Rules.</p>
                </section>
              )}

              <div className="flex flex-wrap gap-2">
                <Link
                  href={`/?pergunta=${encodeURIComponent(`Sobre a carta ${carta}: `)}`}
                  onClick={onFechar}
                  className="inline-flex items-center gap-2 rounded-xl bg-ouro px-4 py-2.5 text-sm font-semibold text-fundo hover:bg-[#e2c06f]"
                >
                  <MessageCircleQuestion size={16} /> Perguntar ao juiz sobre esta carta
                </Link>
                {ficha.url_wiki && (
                  <a
                    href={ficha.url_wiki}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 rounded-xl border border-linha bg-superficie px-4 py-2.5 text-sm hover:bg-superficie-2"
                  >
                    <ExternalLink size={16} /> Wiki
                  </a>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
