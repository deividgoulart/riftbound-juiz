"use client";

// O que todas as telas compartilham: as informações da API (modo público, se sou o dono), a senha e as
// preferências da conta de conclusão (runas básicas, sideboard, ordem dos decks).

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import useSWR from "swr";
import { buscar, guardarToken, pedir, type Info, type Ordem } from "./api";

type Preferencias = { runas: boolean; sideboard: boolean; ordem: Ordem };

type Sessao = {
  info: Info | undefined;
  erroDaInfo: Error | undefined;
  recarregarInfo: () => void;
  podeEditar: boolean;
  entrar: (senha: string) => Promise<void>;
  sair: () => void;
  pedirSenha: boolean;
  setPedirSenha: (abrir: boolean) => void;
  prefs: Preferencias;
  setPrefs: (mudanca: Partial<Preferencias>) => void;
};

const Contexto = createContext<Sessao | null>(null);
const CHAVE_DAS_PREFERENCIAS = "juiz-riftbound:preferencias";
const PADRAO: Preferencias = { runas: true, sideboard: false, ordem: "barato" };

export function ProvedorDaSessao({ children }: { children: React.ReactNode }) {
  const { data: info, error, mutate } = useSWR<Info>("/api/info", buscar, { revalidateOnFocus: false });
  const [pedirSenha, setPedirSenha] = useState(false);
  const [prefs, setPrefsState] = useState<Preferencias>(PADRAO);

  useEffect(() => {
    try {
      const salvas = localStorage.getItem(CHAVE_DAS_PREFERENCIAS);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- só existe no navegador
      if (salvas) setPrefsState({ ...PADRAO, ...JSON.parse(salvas) });
    } catch {
      /* sem localStorage: fica o padrão */
    }
  }, []);

  const setPrefs = useCallback((mudanca: Partial<Preferencias>) => {
    setPrefsState((atual) => {
      const novas = { ...atual, ...mudanca };
      try {
        localStorage.setItem(CHAVE_DAS_PREFERENCIAS, JSON.stringify(novas));
      } catch {
        /* sem localStorage */
      }
      return novas;
    });
  }, []);

  const entrar = useCallback(
    async (senha: string) => {
      const { token } = await pedir<{ token: string | null }>("/api/entrar", {
        method: "POST",
        body: JSON.stringify({ senha }),
      });
      guardarToken(token);
      await mutate();
    },
    [mutate],
  );

  const sair = useCallback(() => {
    guardarToken(null);
    mutate();
  }, [mutate]);

  return (
    <Contexto.Provider
      value={{
        info,
        erroDaInfo: error,
        recarregarInfo: () => mutate(),
        podeEditar: !!info?.dono,
        entrar,
        sair,
        pedirSenha,
        setPedirSenha,
        prefs,
        setPrefs,
      }}
    >
      {children}
    </Contexto.Provider>
  );
}

export function useSessao(): Sessao {
  const sessao = useContext(Contexto);
  if (!sessao) throw new Error("useSessao fora do ProvedorDaSessao");
  return sessao;
}
