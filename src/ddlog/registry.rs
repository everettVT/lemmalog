//! Durable, same-user processor definitions. Registry versions contain no live facts,
//! requests, workers, or runtime state. A host pins a returned immutable version.
//!
//! Writers serialize through a create-new lock file. A crashed writer can leave the
//! lock behind: only an operator who has established writer absence may remove it.
//! Readers never follow a mutable pointer twice when selecting one version.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

pub type Result<T> = std::result::Result<T, String>;
const FORMAT_VERSION: u32 = 1;

/// Exact registered operation selected when the definition was authored. A host
/// must compare all fields to its trusted operation registry before installing it.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RegisteredOperationBinding {
    pub name: String,
    pub version: String,
    pub description: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ProcessorDefinition {
    pub rules: String,
    pub schemas: Value,
    #[serde(default)]
    pub operation: Option<RegisteredOperationBinding>,
}

/// Optional operator-supplied provenance, not an identity or integrity claim.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct GitProvenance {
    pub repository: String,
    pub revision: String,
    #[serde(default)]
    pub path: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ProcessorReference {
    pub processor_id: String,
    pub version: String,
}

/// Checks completed before publication. These describe pure lowering only;
/// successful native DDlog compilation is still required at installation.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DefinitionValidation {
    pub syntax_checked: bool,
    pub types_checked: bool,
    pub supported_lowering_checked: bool,
    pub ddlog_compilation_performed: bool,
}
impl DefinitionValidation {
    fn checked() -> Self {
        Self {
            syntax_checked: true,
            types_checked: true,
            supported_lowering_checked: true,
            ddlog_compilation_performed: false,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ProcessorVersion {
    pub format_version: u32,
    pub processor_id: String,
    /// Content-addressed identifier, distinct from the processor's stable identity.
    pub version: String,
    pub content_sha256: String,
    pub created_at_unix_ms: u64,
    pub git_provenance: Option<GitProvenance>,
    /// The exact source of a fork, retained on every version of the new processor.
    pub lineage: Option<ProcessorReference>,
    pub definition: ProcessorDefinition,
    pub validation: DefinitionValidation,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Current {
    format_version: u32,
    processor_id: String,
    version: String,
    lineage: Option<ProcessorReference>,
}

#[derive(Clone, Debug)]
pub struct ProcessorRegistry {
    root: PathBuf,
}

impl ProcessorRegistry {
    /// Open or create a private registry directory. Existing public directories
    /// are rejected; callers should select a dedicated same-user directory.
    pub fn open(root: PathBuf) -> Result<Self> {
        create_private_dir(&root)?;
        check_private_dir(&root)?;
        Ok(Self { root })
    }

    pub fn create(
        &self,
        definition: ProcessorDefinition,
        provenance: Option<GitProvenance>,
    ) -> Result<ProcessorVersion> {
        validate_definition(&definition)?;
        let _lock = UpdateLock::acquire(&self.root)?;
        self.create_locked(definition, provenance, None)
    }

    /// Publish immutable content and advance the pointer only if the caller read
    /// the expected version. Re-publishing existing content preserves its original
    /// creation time and provenance, including when rolling the pointer back.
    pub fn publish(
        &self,
        processor_id: &str,
        definition: ProcessorDefinition,
        expected_current_version: &str,
        provenance: Option<GitProvenance>,
    ) -> Result<ProcessorVersion> {
        validate_processor_id(processor_id)?;
        validate_version(expected_current_version)?;
        validate_definition(&definition)?;
        let _lock = UpdateLock::acquire(&self.root)?;
        let current = self.current(processor_id)?;
        if current.version != expected_current_version {
            return Err(format!(
                "Current version conflict: expected {expected_current_version}, found {}",
                current.version
            ));
        }
        // Validate the old target before using its lineage or changing the pointer.
        if self.get(processor_id, Some(&current.version))?.lineage != current.lineage {
            return Err("Processor current-version lineage mismatch".into());
        }
        self.publish_locked(processor_id, definition, provenance, current.lineage)
    }

    pub fn fork(
        &self,
        source_id: &str,
        source_version: &str,
        provenance: Option<GitProvenance>,
    ) -> Result<ProcessorVersion> {
        let _lock = UpdateLock::acquire(&self.root)?;
        let source = self.get(source_id, Some(source_version))?;
        self.create_locked(
            source.definition,
            provenance,
            Some(ProcessorReference {
                processor_id: source_id.to_string(),
                version: source_version.to_string(),
            }),
        )
    }

    /// Resolve current once, or read the explicitly selected immutable version.
    pub fn get(&self, processor_id: &str, version: Option<&str>) -> Result<ProcessorVersion> {
        validate_processor_id(processor_id)?;
        let current = if version.is_none() {
            Some(self.current(processor_id)?)
        } else {
            None
        };
        let selected = version
            .map(str::to_string)
            .unwrap_or_else(|| current.as_ref().unwrap().version.clone());
        validate_version(&selected)?;
        let record: ProcessorVersion = read_json(&self.version_path(processor_id, &selected))?;
        if record.format_version != FORMAT_VERSION
            || record.processor_id != processor_id
            || record.version != selected
            || record.validation != DefinitionValidation::checked()
        {
            return Err("Invalid processor version envelope".into());
        }
        validate_lineage(&record.lineage)?;
        if current
            .as_ref()
            .is_some_and(|pointer| pointer.lineage != record.lineage)
        {
            return Err("Processor current-version lineage mismatch".into());
        }
        let hash = definition_hash(&record.definition)?;
        if record.content_sha256 != hash || record.version != format!("sha256:{hash}") {
            return Err("Processor definition content hash mismatch".into());
        }
        validate_definition(&record.definition)?;
        Ok(record)
    }

    fn current(&self, processor_id: &str) -> Result<Current> {
        validate_processor_id(processor_id)?;
        let current: Current = read_json(&self.root.join(processor_id).join("current.json"))?;
        if current.format_version != FORMAT_VERSION || current.processor_id != processor_id {
            return Err("Invalid processor current-version envelope".into());
        }
        validate_version(&current.version)?;
        validate_lineage(&current.lineage)?;
        Ok(current)
    }

    fn create_locked(
        &self,
        definition: ProcessorDefinition,
        provenance: Option<GitProvenance>,
        lineage: Option<ProcessorReference>,
    ) -> Result<ProcessorVersion> {
        let processor_id = format!("processor_{}", random_hex()?);
        let directory = self.root.join(&processor_id);
        // A collision fails closed; identities are never reused or overwritten.
        private_dir_builder().create(&directory).map_err(io_error)?;
        sync_directory(&self.root)?;
        private_dir_builder()
            .create(directory.join("versions"))
            .map_err(io_error)?;
        sync_directory(&directory)?;
        self.publish_locked(&processor_id, definition, provenance, lineage)
    }

    fn publish_locked(
        &self,
        processor_id: &str,
        definition: ProcessorDefinition,
        provenance: Option<GitProvenance>,
        lineage: Option<ProcessorReference>,
    ) -> Result<ProcessorVersion> {
        let content_sha256 = definition_hash(&definition)?;
        let version = format!("sha256:{content_sha256}");
        let path = self.version_path(processor_id, &version);
        let record = match fs::symlink_metadata(&path) {
            Ok(_) => {
                let record = self.get(processor_id, Some(&version))?;
                if record.lineage != lineage {
                    return Err("Processor lineage mismatch".into());
                }
                record
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let record = ProcessorVersion {
                    format_version: FORMAT_VERSION,
                    processor_id: processor_id.to_string(),
                    version: version.clone(),
                    content_sha256,
                    created_at_unix_ms: SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map_err(|error| error.to_string())?
                        .as_millis()
                        .try_into()
                        .map_err(|_| "Creation timestamp overflow")?,
                    git_provenance: provenance,
                    lineage: lineage.clone(),
                    definition,
                    validation: DefinitionValidation::checked(),
                };
                atomic_json(&path, &record, false)?;
                record
            }
            Err(error) => return Err(io_error(error)),
        };
        atomic_json(
            &self.root.join(processor_id).join("current.json"),
            &Current {
                format_version: FORMAT_VERSION,
                processor_id: processor_id.to_string(),
                version,
                lineage,
            },
            true,
        )?;
        Ok(record)
    }

    fn version_path(&self, processor_id: &str, version: &str) -> PathBuf {
        // Public callers validate both identifiers before path construction.
        self.root
            .join(processor_id)
            .join("versions")
            .join(format!("{}.json", &version[7..]))
    }
}

fn validate_definition(definition: &ProcessorDefinition) -> Result<()> {
    if let Some(operation) = &definition.operation {
        super::operations::lower_registered_program(
            &operation.name,
            &operation.version,
            &definition.rules,
            definition.schemas.clone(),
        )?;
    } else {
        let schemas: BTreeMap<String, super::Schema> =
            serde_json::from_value(definition.schemas.clone())
                .map_err(|error| error.to_string())?;
        super::lower(&definition.rules, &schemas)?;
    }
    Ok(())
}

fn definition_hash(definition: &ProcessorDefinition) -> Result<String> {
    // JSON object keys are recursively ordered so map insertion order cannot
    // affect identity. Exact authored text and operation definitions do affect it.
    fn canonical(value: Value) -> Value {
        match value {
            Value::Object(map) => Value::Object(
                map.into_iter()
                    .map(|(key, value)| (key, canonical(value)))
                    .collect::<BTreeMap<_, _>>()
                    .into_iter()
                    .collect(),
            ),
            Value::Array(values) => Value::Array(values.into_iter().map(canonical).collect()),
            value => value,
        }
    }
    let bytes = serde_json::to_vec(&canonical(
        serde_json::to_value(definition).map_err(|error| error.to_string())?,
    ))
    .map_err(|error| error.to_string())?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn validate_processor_id(id: &str) -> Result<()> {
    if !id.starts_with("processor_") || !is_hex(&id[10..], 32) {
        return Err("Invalid processor identity".into());
    }
    Ok(())
}
fn validate_version(version: &str) -> Result<()> {
    if !version.starts_with("sha256:") || !is_hex(&version[7..], 64) {
        return Err("Invalid processor version".into());
    }
    Ok(())
}
fn is_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}
fn validate_lineage(lineage: &Option<ProcessorReference>) -> Result<()> {
    if let Some(source) = lineage {
        validate_processor_id(&source.processor_id)?;
        validate_version(&source.version)?;
    }
    Ok(())
}

fn random_hex() -> Result<String> {
    let mut bytes = [0_u8; 16];
    File::open("/dev/urandom")
        .and_then(|mut source| source.read_exact(&mut bytes))
        .map_err(io_error)?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}
fn io_error(error: std::io::Error) -> String {
    error.to_string()
}
fn private_dir_builder() -> fs::DirBuilder {
    let mut builder = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder
}
fn create_private_dir(path: &Path) -> Result<()> {
    match private_dir_builder().create(path) {
        Ok(()) => sync_directory(
            path.parent()
                .filter(|p| !p.as_os_str().is_empty())
                .unwrap_or(Path::new(".")),
        ),
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => Ok(()),
        Err(error) => Err(io_error(error)),
    }
}
fn check_private_dir(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path).map_err(io_error)?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("Registry must be a directory, not a symbolic link".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o077 != 0 {
            return Err("Registry directory must be private to its owner (mode 0700)".into());
        }
    }
    #[cfg(not(unix))]
    return Err("Private local processor registries require Unix permissions".into());
    #[allow(unreachable_code)]
    Ok(())
}
fn private_file(path: &Path) -> std::io::Result<File> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options.open(path)
}
fn sync_directory(path: &Path) -> Result<()> {
    File::open(path)
        .and_then(|file| file.sync_all())
        .map_err(io_error)
}
fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T> {
    let metadata = fs::symlink_metadata(path).map_err(io_error)?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err("Registry records must be regular files".into());
    }
    serde_json::from_slice(&fs::read(path).map_err(io_error)?)
        .map_err(|error| format!("Invalid registry record {}: {error}", path.display()))
}

fn atomic_json<T: Serialize>(path: &Path, value: &T, replace: bool) -> Result<()> {
    let bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    let directory = path.parent().ok_or("Missing record directory")?;
    let temporary = directory.join(format!(".write-{}", random_hex()?));
    let result = (|| {
        let mut file = private_file(&temporary).map_err(io_error)?;
        file.write_all(&bytes).map_err(io_error)?;
        file.sync_all().map_err(io_error)?;
        if replace {
            fs::rename(&temporary, path).map_err(io_error)?;
        } else {
            // Atomic no-replace publication keeps historical versions immutable.
            fs::hard_link(&temporary, path).map_err(io_error)?;
            fs::remove_file(&temporary).map_err(io_error)?;
        }
        sync_directory(directory).map_err(|error| {
            format!("Registry publication durability uncertain; inspect before retrying: {error}")
        })
    })();
    let _ = fs::remove_file(&temporary);
    result
}

struct UpdateLock {
    path: PathBuf,
}
impl UpdateLock {
    fn acquire(root: &Path) -> Result<Self> {
        check_private_dir(root)?;
        let path = root.join(".update.lock");
        let mut file = private_file(&path).map_err(|error| {
            if error.kind() == std::io::ErrorKind::AlreadyExists {
                "Registry update lock exists; another writer may be active. A stale lock requires operator reconciliation; it is never removed automatically".into()
            } else {
                io_error(error)
            }
        })?;
        let lock = Self { path };
        writeln!(file, "pid={}", std::process::id()).map_err(io_error)?;
        file.sync_all().map_err(io_error)?;
        sync_directory(root)?;
        Ok(lock)
    }
}
impl Drop for UpdateLock {
    fn drop(&mut self) {
        if fs::remove_file(&self.path).is_ok() {
            if let Some(root) = self.path.parent() {
                let _ = sync_directory(root);
            }
        }
    }
}
