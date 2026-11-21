use anyhow::{anyhow, bail, Context, Result};
use dlib_face_recognition::{
    FaceDetector, FaceDetectorCnn, FaceDetectorTrait, FaceEncoderNetwork, FaceEncoderTrait,
    FaceEncoding, ImageMatrix, LandmarkPredictor, LandmarkPredictorTrait,
};
use image::{codecs::jpeg::JpegEncoder, ImageBuffer, Rgb, RgbImage};
use serde_json::{json, Value};
use std::{env, fs, io::Write, os::unix::fs::PermissionsExt, path::{Path, PathBuf}, process::Command,
          sync::{atomic::{AtomicBool, Ordering}, Arc}, time::{Duration, Instant, SystemTime, UNIX_EPOCH}};
use v4l::{buffer::Type, io::mmap::Stream as MmapStream, io::traits::CaptureStream, video::Capture, Device};

const CONFIG: &str = "/etc/howdy/config.ini";
const LIT_FRAME_MIN_MEAN: f64 = 10.0; // Reject frames too dark for a useful preview.
const LIT_FRAME_MIN_CONTRAST: f64 = 5.0; // Also reject this camera's flat gray frames.

fn runtime() -> PathBuf {
    let base = env::var("XDG_RUNTIME_DIR")
        .unwrap_or_else(|_| format!("/run/user/{}", unsafe { libc::geteuid() }));
    Path::new(&base).join("omarchy-howdy-wizard")
}

fn output(value: Value) { println!("{value}"); }

fn ini(section: &str, key: &str, fallback: &str) -> String {
    let mut current = "";
    if let Ok(raw) = fs::read_to_string(CONFIG) {
        for line in raw.lines() {
            let line = line.trim();
            if line.starts_with('[') && line.ends_with(']') { current = &line[1..line.len()-1]; }
            if current == section {
                if let Some((name, value)) = line.split_once('=') {
                    if name.trim() == key { return value.split('#').next().unwrap_or("").trim().to_owned(); }
                }
            }
        }
    }
    fallback.to_owned()
}

fn cameras() -> Result<Vec<Value>> {
    let mut nodes: Vec<_> = fs::read_dir("/dev")?.flatten()
        .filter_map(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            name.strip_prefix("video").and_then(|n| n.parse::<u32>().ok())
                .map(|n| (n, entry.path()))
        }).collect();
    nodes.sort_by_key(|(n, _)| *n);
    let aliases: Vec<_> = fs::read_dir("/dev/v4l/by-id").into_iter().flatten().flatten()
        .map(|entry| entry.path()).collect();
    let mut found = Vec::new();
    for (_, node) in nodes {
        let result = Command::new("v4l2-ctl").args(["-d", &node.to_string_lossy(), "--list-formats"]).output();
        let Ok(result) = result else { continue };
        let raw = String::from_utf8_lossy(&result.stdout);
        let formats: Vec<String> = raw.lines().filter_map(|line| {
            let (_, suffix) = line.split_once('\'')?;
            let (name, _) = suffix.split_once('\'')?;
            (name.len() == 4).then(|| name.to_owned())
        }).collect();
        if formats.is_empty() { continue; }
        let real = fs::canonicalize(&node)?;
        let mut stable: Vec<_> = aliases.iter().filter(|path| fs::canonicalize(path).ok().as_ref() == Some(&real)).collect();
        stable.sort();
        let path = stable.first().map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_else(|| node.to_string_lossy().into_owned());
        let node_name = node.file_name().unwrap().to_string_lossy();
        let name = fs::read_to_string(format!("/sys/class/video4linux/{node_name}/name"))
            .unwrap_or_else(|_| node_name.into_owned()).trim().to_owned();
        found.push(json!({"path":path,"node":node,"name":name,
                          "recommended":formats.len()==1 && formats[0]=="GREY","formats":formats}));
    }
    Ok(found)
}

fn status() -> Value {
    let user = env::var("USER").unwrap_or_default();
    let model = Path::new("/etc/howdy/models").join(format!("{user}.dat"));
    let run = runtime();
    let marker = "# managed by Howdy Face Unlock (io.github.tslove923.howdy-face-unlock)";
    let pam_wired = ["/etc/pam.d/sudo", "/etc/pam.d/polkit-1"].iter().all(|path|
        fs::read_to_string(path).map(|s| s.lines().any(|line| line == marker)).unwrap_or(false));
    json!({"installed":Path::new(CONFIG).exists(),
           "camera":ini("video","device_path",""),"enrolled":model.exists(),
           "sudoPolkitEnabled":pam_wired,
           "modelReadable":fs::File::open(&model).is_ok(),
           "preview":run.join("preview.jpg"),"state":run.join("state.json")})
}

fn theme() -> Result<Value> {
    let path = Path::new(&env::var("HOME")?).join(".local/state/omarchy/current/theme/colors.toml");
    if !path.exists() { return Ok(json!({})); }
    Ok(serde_json::to_value(fs::read_to_string(path)?.parse::<toml::Value>()?)?)
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    let tmp = path.with_extension("tmp");
    let mut f = fs::File::create(&tmp)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    fs::rename(tmp, path)?;
    Ok(())
}

fn state(value: Value) -> Result<()> {
    let run = runtime();
    fs::create_dir_all(&run)?;
    fs::set_permissions(&run, fs::Permissions::from_mode(0o700))?;
    write_atomic(&run.join("state.json"), value.to_string().as_bytes())
}

fn now() -> f64 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64() }

enum Detector { Hog(FaceDetector), Cnn(FaceDetectorCnn) }
struct Recognizer {
    detector: Detector,
    predictor: LandmarkPredictor,
    encoder: FaceEncoderNetwork,
    enrolled: Vec<FaceEncoding>,
    threshold: f64,
}

impl Recognizer {
    fn new(user: &str) -> Result<Self> {
        let data = Path::new("/usr/share/dlib-data");
        let detector = if ini("core", "use_cnn", "false").eq_ignore_ascii_case("true") {
            Detector::Cnn(FaceDetectorCnn::open(data.join("mmod_human_face_detector.dat")).map_err(|e| anyhow!(e))?)
        } else { Detector::Hog(FaceDetector::new()) };
        let predictor = LandmarkPredictor::open(data.join("shape_predictor_5_face_landmarks.dat")).map_err(|e| anyhow!(e))?;
        let encoder = FaceEncoderNetwork::open(data.join("dlib_face_recognition_resnet_model_v1.dat")).map_err(|e| anyhow!(e))?;
        let path = Path::new("/etc/howdy/models").join(format!("{user}.dat"));
        let mut enrolled = Vec::new();
        if path.exists() {
            let models: Value = serde_json::from_slice(&fs::read(&path).with_context(|| format!("Cannot read {}", path.display()))?)?;
            for model in models.as_array().ok_or_else(|| anyhow!("Invalid Howdy model file"))? {
                if let Some(samples) = model.get("data").and_then(Value::as_array) {
                    for sample in samples {
                        let values: Vec<f64> = sample.as_array().ok_or_else(|| anyhow!("Invalid Howdy encoding"))?
                            .iter().map(|x| x.as_f64().ok_or_else(|| anyhow!("Invalid Howdy encoding value"))).collect::<Result<_>>()?;
                        enrolled.push(FaceEncoding::from_vec(&values).map_err(|e| anyhow!(e.to_string()))?);
                    }
                }
            }
        }
        let threshold = ini("video", "certainty", "3.5").parse::<f64>()? / 10.0;
        Ok(Self { detector, predictor, encoder, enrolled, threshold })
    }

    fn check(&self, frame: &RgbImage) -> (String, Option<f64>) {
        let matrix = ImageMatrix::from_image(frame);
        let faces = match &self.detector {
            Detector::Hog(d) => d.face_locations(&matrix),
            Detector::Cnn(d) => d.face_locations(&matrix),
        };
        if faces.is_empty() { return ("no-face".into(), None); }
        if self.enrolled.is_empty() { return ("no-model".into(), None); }
        let landmarks: Vec<_> = faces.iter().map(|face| self.predictor.face_landmarks(&matrix, face)).collect();
        let encodings = self.encoder.get_face_encodings(&matrix, &landmarks, 1);
        let best = encodings.iter().flat_map(|encoding| self.enrolled.iter().map(move |saved| encoding.distance(saved)))
            .fold(f64::INFINITY, f64::min);
        if !best.is_finite() { return ("no-match".into(), None); }
        ((if best > 0.0 && best < self.threshold { "match" } else { "no-match" }).into(), Some(best * 10.0))
    }
}

fn decode(buf: &[u8], format: &v4l::format::Format) -> Result<(RgbImage, f64)> {
    let width = format.width as usize;
    let height = format.height as usize;
    let tag = format.fourcc.to_string();
    if tag == "MJPG" {
        let image = image::load_from_memory_with_format(buf, image::ImageFormat::Jpeg)?.to_rgb8();
        let mean = image.pixels().map(|p| (p[0] as f64 + p[1] as f64 + p[2] as f64) / 3.0).sum::<f64>()
            / (image.width() * image.height()) as f64;
        return Ok((image, mean));
    }
    let stride = if format.stride == 0 { width * (if tag == "YUYV" { 2 } else { 1 }) }
                 else { format.stride as usize };
    let mut rgb = Vec::with_capacity(width * height * 3);
    let mut sum = 0u64;
    for y in 0..height {
        let row = buf.get(y*stride..(y+1)*stride).ok_or_else(|| anyhow!("Short camera frame"))?;
        for x in 0..width {
            let luma = match tag.as_str() {
                "GREY" => *row.get(x).ok_or_else(|| anyhow!("Short camera row"))?,
                "YUYV" => *row.get(x*2).ok_or_else(|| anyhow!("Short camera row"))?,
                _ => bail!("Unsupported camera pixel format {tag}"),
            };
            sum += luma as u64;
            rgb.extend_from_slice(&[luma,luma,luma]);
        }
    }
    Ok((ImageBuffer::<Rgb<u8>, Vec<u8>>::from_raw(width as u32,height as u32,rgb)
        .ok_or_else(|| anyhow!("Bad camera dimensions"))?, sum as f64 / (width*height) as f64))
}

fn frame_contrast(frame: &RgbImage) -> f64 {
    // Ignore edge rows, where this camera puts a dark sync line even in an
    // otherwise uniform gray frame. Sampling every fourth pixel is sufficient.
    let (width, height) = frame.dimensions();
    let (x0, x1, y0, y1) = (width / 10, width * 9 / 10, height / 10, height * 9 / 10);
    let (mut count, mut sum, mut square) = (0f64, 0f64, 0f64);
    for y in (y0..y1).step_by(4) {
        for x in (x0..x1).step_by(4) {
            let pixel = frame.get_pixel(x, y);
            let luma = (pixel[0] as f64 + pixel[1] as f64 + pixel[2] as f64) / 3.0;
            count += 1.0;
            sum += luma;
            square += luma * luma;
        }
    }
    if count == 0.0 { return 0.0; }
    (square / count - (sum / count).powi(2)).max(0.0).sqrt()
}

fn stream(device_path: &str, user: &str, mode: &str) -> Result<()> {
    if mode != "preview" && mode != "verify" { bail!("Invalid preview mode"); }
    let camera = cameras()?.into_iter().find(|c| c["path"] == device_path)
        .ok_or_else(|| anyhow!("Camera is no longer available. Rescan cameras."))?;
    let run = runtime();
    fs::create_dir_all(&run)?;
    fs::set_permissions(&run, fs::Permissions::from_mode(0o700))?;
    for name in ["preview.jpg", "state.json"] { let _ = fs::remove_file(run.join(name)); }
    let dev = Device::with_path(device_path).context("Camera could not open. Close other apps using it and retry")?;
    let format = dev.format()?;
    let ir = format.fourcc.to_string() == "GREY" || camera["name"].as_str()
        .unwrap_or("").to_ascii_lowercase().contains("ir camera");
    let recognizer = if mode == "verify" { Some(Recognizer::new(user)?) } else { None };
    let mut capture = MmapStream::with_buffers(&dev, Type::VideoCapture, 4)?;
    let stopped = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGTERM, Arc::clone(&stopped))?;
    let mut last_publish = Instant::now() - Duration::from_secs(1);
    let mut last_lit = Instant::now();
    let mut last_check = Instant::now() - Duration::from_secs(1);
    let mut result = "starting".to_owned();
    let mut distance = None;
    let mut has_frame = false;
    while !stopped.load(Ordering::Relaxed) {
        let (buf, _) = match capture.next() {
            Ok(frame) => frame,
            Err(_) if stopped.load(Ordering::Relaxed) => break,
            Err(error) => return Err(error).context("Camera stopped delivering frames"),
        };
        let (frame, mean) = decode(buf, &format)?;
        if ir && (mean < LIT_FRAME_MIN_MEAN || frame_contrast(&frame) < LIT_FRAME_MIN_CONTRAST) {
            if last_lit.elapsed() > Duration::from_secs(2) && last_publish.elapsed() > Duration::from_millis(800) {
                result = "dark".into();
                state(json!({"result":result,"distance":null,"threshold":recognizer.as_ref().map(|r|r.threshold*10.0),"frame":has_frame,"at":now()}))?;
                last_publish = Instant::now();
            }
            continue;
        }
        last_lit = Instant::now();
        if last_publish.elapsed() < Duration::from_millis(180) { continue; }
        if let Some(ref recognizer) = recognizer {
            if last_check.elapsed() > Duration::from_millis(550) {
                (result, distance) = recognizer.check(&frame);
                last_check = Instant::now();
            }
        } else { result = "preview".into(); }
        let mut jpeg = Vec::new();
        JpegEncoder::new_with_quality(&mut jpeg, 78).encode_image(&frame)?;
        write_atomic(&run.join("preview.jpg"), &jpeg)?;
        has_frame = true;
        state(json!({"result":result,"distance":distance.map(|d:f64|(d*100.0).round()/100.0),
                     "threshold":recognizer.as_ref().map(|r|(r.threshold*1000.0).round()/100.0),"frame":true,"at":now()}))?;
        last_publish = Instant::now();
    }
    for name in ["preview.jpg","state.json"] { let _ = fs::remove_file(run.join(name)); }
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let result = (|| -> Result<()> {
        match args.get(1).map(String::as_str) {
            Some("cameras") => output(json!(cameras()?)),
            Some("status") => output(status()),
            Some("theme") => output(theme()?),
            Some("state") => {
                let path = runtime().join("state.json");
                output(if path.exists() { serde_json::from_slice(&fs::read(path)?)? } else { json!({"result":"starting"}) });
            }
            Some("stream") => stream(args.get(2).ok_or_else(||anyhow!("Missing camera"))?,
                                      args.get(3).ok_or_else(||anyhow!("Missing user"))?,
                                      args.get(4).ok_or_else(||anyhow!("Missing mode"))?)?,
            _ => bail!("Unknown action"),
        }
        Ok(())
    })();
    if let Err(error) = result { output(json!({"error":format!("{error:#}")})); std::process::exit(1); }
}
