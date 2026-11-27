import * as fs from "fs";
import * as path from "path";
import * as semver from "semver";

type Channel = "stable" | "beta" | "lts";
type SizeTier = "tiny" | "standard" | "large" | "oversize";

const VALID_CHANNELS: ReadonlySet<string> = new Set<Channel>([
  "stable",
  "beta",
  "lts",
]);

const ARTIFACT_PATH_PATTERN =
  /^[a-z0-9-]+\/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$/;

interface ArtifactInput {
  raw_path: string;
  channel: string;
  size_kb: number;
}

interface GateInput {
  min_range: string;
  artifacts: ArtifactInput[];
}

interface GateOutput {
  total: number;
  eligible: number;
  oversize: number;
  total_kb: number;
  max_kb: number;
}

interface EvaluatedArtifact {
  input: ArtifactInput;
  norm: string | null;
  pkg: string | null;
  ver: string | null;
  sizeTier: SizeTier;
  validFormat: boolean;
  eligible: boolean;
}

function decodeAndNormalizePath(rawPath: string): string | null {
  try {
    const decoded = decodeURIComponent(rawPath);
    return path.posix.normalize(decoded);
  } catch {
    return null;
  }
}

function isValidChannel(channel: string): channel is Channel {
  return VALID_CHANNELS.has(channel);
}

function isEligibleVersion(ver: string, minRange: string): boolean {
  const parsed = semver.parse(ver);
  if (parsed === null || parsed.prerelease.length > 0) {
    return false;
  }
  return semver.satisfies(parsed, minRange, { includePrerelease: false });
}

function classifySizeTier(sizeKb: number): SizeTier {
  if (sizeKb < 100) {
    return "tiny";
  }
  if (sizeKb <= 1000) {
    return "standard";
  }
  if (sizeKb <= 5000) {
    return "large";
  }
  return "oversize";
}

function evaluateArtifact(
  artifact: ArtifactInput,
  minRange: string,
): EvaluatedArtifact {
  const sizeTier = classifySizeTier(artifact.size_kb);
  const norm = decodeAndNormalizePath(artifact.raw_path);
  if (norm === null) {
    return {
      input: artifact,
      norm: null,
      pkg: null,
      ver: null,
      sizeTier,
      validFormat: false,
      eligible: false,
    };
  }

  const ver = path.posix.basename(norm);
  const pkg = path.posix.dirname(norm);
  const validFormat =
    ARTIFACT_PATH_PATTERN.test(norm) && isValidChannel(artifact.channel);
  const eligible =
    validFormat && sizeTier !== "oversize" && isEligibleVersion(ver, minRange);

  return {
    input: artifact,
    norm,
    pkg,
    ver,
    sizeTier,
    validFormat,
    eligible,
  };
}

function evaluateGate(input: GateInput): GateOutput {
  let eligibleCount = 0;
  let oversizeCount = 0;
  let totalKb = 0;
  let maxKb = 0;

  for (let i = 0; i < input.artifacts.length; i++) {
    const artifact = input.artifacts[i];
    const evaluated = evaluateArtifact(artifact, input.min_range);

    if (evaluated.eligible) {
      eligibleCount += 1;
    }
    if (evaluated.sizeTier === "oversize") {
      oversizeCount += 1;
    }

    totalKb += artifact.size_kb;
    if (i === 0 || artifact.size_kb > maxKb) {
      maxKb = artifact.size_kb;
    }
  }

  return {
    total: input.artifacts.length,
    eligible: eligibleCount,
    oversize: oversizeCount,
    total_kb: totalKb,
    max_kb: maxKb,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const parsedInput = JSON.parse(rawInput) as GateInput;
  const result = evaluateGate(parsedInput);
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main();
