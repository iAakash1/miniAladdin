import SiteHeader from '@/components/marketing/SiteHeader'
import SiteFooter from '@/components/marketing/SiteFooter'

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main id="main">{children}</main>
      <SiteFooter />
    </>
  )
}
