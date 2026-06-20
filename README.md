<div align="center">
    <img src="resources/branding/app_icon/raw.png"
        title="Nitrous" alt="Nitrous logo" width="120" />
    <h1>Nitrous</h1>
    <p>
        The Chromium-based web browser made for people, with love.
        <br>
        Privacy-first with unbiased ad-blocking. No bloat and no noise.
    </p>
    <a href="https://helium.computer/">
        helium.computer
    </a>
</div>

## Downloads
> [!NOTE]
> Nitrous is currently in beta, so unexpected issues may occur.
> Please report them if they haven't already been reported.

The easiest way to download Nitrous is [helium.computer](https://helium.computer/).
It'll pick a compatible binary for your platform automatically.

The same releases can also be downloaded from source on GitHub:

- [Latest macOS release](https://github.com/imputnet/helium-macos/releases/latest)
- [Latest Linux release](https://github.com/imputnet/helium-linux/releases/latest)
- [Latest Windows release](https://github.com/imputnet/helium-windows/releases/latest)

## Nitrous repos
All Nitrous packaging, tooling, services, and components are open source
and published on GitHub.

### Platform packaging and tooling
- [Nitrous for macOS](https://github.com/imputnet/helium-macos)
- [Nitrous for Linux](https://github.com/imputnet/helium-linux)
- [Nitrous for Windows](https://github.com/imputnet/helium-windows)

### Web services and Nitrous components
- [Nitrous services](https://github.com/imputnet/helium-services)
- [Nitrous onboarding](https://github.com/imputnet/helium-onboarding)
- [Nitrous fork of uBlock Origin](https://github.com/imputnet/uBlock)

## Development
macOS is our primary development platform, so it's the recommended
development environment for community contributions.

Linux packaging includes a similar development script, so the same guide
can be applied there too.

[> See development docs in macOS repo](https://github.com/imputnet/helium-macos/blob/main/docs/building.md#development-build-and-environment)

## Contributing
Before contributing to Nitrous, please read the guidelines in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

### The Chromium project
[The Chromium Project](https://www.chromium.org/) is at the core of Nitrous,
making it possible in the first place.

### ungoogled-chromium
This repo is based on [ungoogled-chromium](https://github.com/ungoogled-software/ungoogled-chromium),
but heavily modified for Nitrous. Special thanks to everyone behind ungoogled-chromium,
they made working with Chromium way easier.

### Other Chromium browsers

Nitrous includes some patches from other open source Chromium browsers:

- [Inox patchset](https://github.com/gcarq/inox-patchset)
- [Debian](https://tracker.debian.org/pkg/chromium-browser)
- [Bromite](https://github.com/bromite/bromite)
- [Iridium Browser](https://iridiumbrowser.de/)
- [Brave](https://github.com/brave/brave-core)

All patches are sorted by vendor in the [patches](patches/) directory of this repo.

## License
All code, patches, modified portions of imported code or patches, and
any other content that is unique to Nitrous and not imported from other
repositories is licensed under GPL-3.0. See [LICENSE](LICENSE).

Any content imported from other projects retains its original license (for
example, any original unmodified code imported from ungoogled-chromium remains
licensed under their [BSD 3-Clause license](LICENSE.ungoogled_chromium)).
