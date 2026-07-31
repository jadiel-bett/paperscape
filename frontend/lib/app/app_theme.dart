import 'package:flutter/material.dart';

const paperScapeInk = Color(0xFF07111F);
const paperScapeCanvas = Color(0xFFF5F7FB);
const paperScapeBlue = Color(0xFF0F62FE);
const paperScapeCyan = Color(0xFF12CFEF);
const paperScapeViolet = Color(0xFF8A3FFC);
const paperScapeMutedInk = Color(0xFF526175);

ThemeData buildPaperScapeTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: paperScapeBlue,
    brightness: Brightness.light,
  ).copyWith(
    primary: paperScapeBlue,
    onPrimary: Colors.white,
    secondary: paperScapeViolet,
    onSecondary: Colors.white,
    surface: Colors.white,
    onSurface: paperScapeInk,
    surfaceContainerHighest: const Color(0xFFE9EEF7),
    outline: const Color(0xFFB4C0D2),
    outlineVariant: const Color(0xFFD9E1ED),
    error: const Color(0xFFB42318),
    errorContainer: const Color(0xFFFFE4E1),
  );

  return ThemeData(
    colorScheme: scheme,
    scaffoldBackgroundColor: paperScapeCanvas,
    useMaterial3: true,
    fontFamily: 'IBM Plex Sans',
    fontFamilyFallback: const ['Arial', 'sans-serif'],
    textTheme: const TextTheme(
      displayLarge: TextStyle(
        color: paperScapeInk,
        fontSize: 56,
        height: 1.02,
        fontWeight: FontWeight.w700,
        letterSpacing: -2.2,
      ),
      displaySmall: TextStyle(
        color: paperScapeInk,
        fontSize: 40,
        height: 1.05,
        fontWeight: FontWeight.w700,
        letterSpacing: -1.2,
      ),
      headlineSmall: TextStyle(
        color: paperScapeInk,
        fontSize: 28,
        height: 1.15,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.6,
      ),
      titleLarge: TextStyle(
        color: paperScapeInk,
        fontSize: 22,
        height: 1.2,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.3,
      ),
      titleMedium: TextStyle(
        color: paperScapeInk,
        fontSize: 17,
        height: 1.25,
        fontWeight: FontWeight.w700,
      ),
      bodyLarge: TextStyle(
        color: paperScapeInk,
        fontSize: 16,
        height: 1.5,
      ),
      bodyMedium: TextStyle(
        color: paperScapeMutedInk,
        fontSize: 14,
        height: 1.45,
      ),
      labelLarge: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.1,
      ),
      labelMedium: TextStyle(
        color: paperScapeMutedInk,
        fontSize: 11,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.8,
      ),
    ),
    cardTheme: CardTheme(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: const BorderSide(color: Color(0xFFDCE4EF)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: paperScapeBlue,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: paperScapeBlue,
        side: const BorderSide(color: Color(0xFF8FA4C0)),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: paperScapeBlue,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: const Color(0xFFEFF4FF),
      side: BorderSide.none,
      labelStyle: const TextStyle(
        color: paperScapeBlue,
        fontWeight: FontWeight.w700,
        fontSize: 12,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
  );
}
