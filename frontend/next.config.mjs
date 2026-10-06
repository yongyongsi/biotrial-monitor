/** @type {import('next').NextConfig} */

// 세 가지 방식으로 빌드한다.
//   기본          -> standalone 서버 (Docker / 클라우드)
//   NEXT_EXPORT   -> 정적 파일 (휴대폰: FastAPI 가 서빙)
//   + BASE_PATH   -> GitHub Pages (주소가 /저장소이름/ 아래에 놓인다)
const isExport = process.env.NEXT_EXPORT === "1";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  output: isExport ? "export" : "standalone",
  basePath: basePath || undefined,
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
