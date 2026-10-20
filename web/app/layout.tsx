import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'TraceLens · Incident workspace',description:'Evidence-backed incident investigation research application'};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){
  return <html lang="en"><body>{children}</body></html>;
}
