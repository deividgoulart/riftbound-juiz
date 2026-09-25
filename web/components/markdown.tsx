import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

// A resposta do juiz é Markdown com as citações em <sup><a>. O texto do LLM já chega sem HTML
// (html.escape na API); mesmo assim, só <sup> e <a> passam por aqui.
const esquema = {
  ...defaultSchema,
  attributes: { ...defaultSchema.attributes, a: [...(defaultSchema.attributes?.a ?? []), "target", "rel"] },
};

export function Markdown({ texto, className = "resposta" }: { texto: string; className?: string }) {
  return (
    <div className={className}>
      <ReactMarkdown
        rehypePlugins={[rehypeRaw, [rehypeSanitize, esquema]]}
        // eslint-disable-next-line @typescript-eslint/no-unused-vars -- "node" não pode ir pro <a>
        components={{ a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" /> }}
      >
        {texto}
      </ReactMarkdown>
    </div>
  );
}
