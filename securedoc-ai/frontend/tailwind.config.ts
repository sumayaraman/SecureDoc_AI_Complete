import type {Config} from 'tailwindcss'
const config:Config={content:['./app/**/*.{ts,tsx}','./components/**/*.{ts,tsx}','./lib/**/*.{ts,tsx}'],theme:{extend:{colors:{ink:'#0b1220',muted:'#64748b',brand:'#4f46e5',surface:'#f8fafc'},boxShadow:{soft:'0 12px 40px rgba(15,23,42,.06)'}}},plugins:[]}
export default config
