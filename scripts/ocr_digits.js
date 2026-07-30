/**
 * OCR a digit captcha image. Usage: node scripts/ocr_digits.js <image-path>
 * Prints only the recognized digits to stdout.
 */
const fs = require("fs");
const path = require("path");

async function main() {
  const imgPath = process.argv[2];
  if (!imgPath || !fs.existsSync(imgPath)) {
    console.error("usage: node scripts/ocr_digits.js <image>");
    process.exit(2);
  }
  let Tesseract;
  try {
    Tesseract = require("tesseract.js");
  } catch {
    console.error("tesseract.js not installed (npm i tesseract.js)");
    process.exit(3);
  }
  const { data } = await Tesseract.recognize(path.resolve(imgPath), "eng", {
    tessedit_char_whitelist: "0123456789",
  });
  const digits = String(data.text || "").replace(/\D/g, "");
  process.stdout.write(digits);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
