/** @type {import('next').NextConfig} */

// 세 가지 방식으로 빌드한다.
//   기본          -> standalone 서버 (Docker / 클라우드)
//   NEXT_EXPORT   -> 정적 파일 (휴대폰: FastAPI 가 서빙 / GitHub Pages)
//   + BASE_PATH   -> GitHub Pages (주소가 /저장소이름/ 아래에 놓인다)
const isExport = process.env.NEXT_EXPORT === "1";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

// 화면은 언제나 같은 주소의 /data/*.json 을 읽는다.
// 휴대폰·GitHub Pages 에서는 그 주소에 파일이 그대로 있지만,
// Docker 에서는 화면(3000)과 데이터(8000)가 분리돼 있어 여기서 이어준다.
const apiTarget = process.env.API_PROXY_TARGET || "http://localhost:8000";

const nextConfig = {
  output: isExport ? "export" : "standalone",
  basePath: basePath || undefined,
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },

  async rewrites() {
    if (isExport) return [];          // 정적 내보내기에서는 rewrite 를 쓸 수 없다
    return [
      { source: "/data/:path*", destination: `${apiTarget}/data/:path*` },
      { source: "/api/:path*", destination: `${apiTarget}/api/:path*` },
    ];
  },
};

export default nextConfig;
