import { Room } from "@/app/Room";
import dynamic from "next/dynamic";
const CollaborativeEditor = dynamic(() => import("@/components/CollaborativeEditor"), { ssr: false });

export default function Home() {
  return (
    <main>
      <Room>
        <CollaborativeEditor />
      </Room>
    </main>
  );
}
