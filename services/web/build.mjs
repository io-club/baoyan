import { build } from 'esbuild';
await build({entryPoints:['src/main.js'],bundle:true,minify:true,format:'esm',target:['es2022'],outfile:'public/ui-shell.js',legalComments:'eof',define:{'process.env.NODE_ENV':'"production"','__VUE_OPTIONS_API__':'true','__VUE_PROD_DEVTOOLS__':'false','__VUE_PROD_HYDRATION_MISMATCH_DETAILS__':'false'}});
