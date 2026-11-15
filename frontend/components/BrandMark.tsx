/** Parallax mark: a flying squirrel peeking over Nassau Hall (HackPrinceton). From Kelly's lease-validation branch. */
export default function BrandMark() {
  return (
    <svg className="brand-squirrel" viewBox="0 0 212 98" fill="none" role="img" aria-label="A cute flying squirrel peeking above the roof of Nassau Hall saying HackPrinceton">
    <path d="M12 87h132" stroke="#B4BFC4" strokeWidth="2" strokeLinecap="round" />
    {/* The squirrel sits behind the building; the facade hides its lower body. */}
    <g transform="translate(77 1) scale(0.83)">
    <path d="M47 31C58 31 69 22 65 12 62 4 49 6 47 14c-2 6 7 7 8 2 4 7-4 10-10 10" fill="#C48857" stroke="#704931" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
    {/* Round belly, one relaxed arm and one raised waving paw. */}
    <ellipse cx="34" cy="43" rx="16" ry="17" fill="#C48857" stroke="#704931" strokeWidth="2.2" />
    <ellipse cx="33" cy="43" rx="11" ry="14" fill="#F9E8CE" />
    <g transform="translate(68 0) scale(-1 1)">
    <path d="M23 35q-9 4-8 14" stroke="#704931" strokeWidth="8" strokeLinecap="round" />
    <path d="M23 35q-9 4-8 14" stroke="#C48857" strokeWidth="4" strokeLinecap="round" />
    <path d="M47 35q10-3 10-15" stroke="#704931" strokeWidth="8" strokeLinecap="round" />
    <path d="M47 35q10-3 10-15" stroke="#C48857" strokeWidth="4" strokeLinecap="round" />
    <ellipse cx="57" cy="17" rx="4.5" ry="6" transform="rotate(-10 57 17)" fill="#C48857" stroke="#704931" strokeWidth="1.7" />
    <path d="m69 14 2-3m-3 13 4 1" stroke="#D6A059" strokeWidth="1.7" strokeLinecap="round" />
    </g>
    <path d="m20 19-1-9c0-4 4-5 7-1l4 6m9 3 5-7c3-4 7-2 6 2l-2 10" fill="#C48857" stroke="#704931" strokeWidth="2.2" strokeLinejoin="round" />
    <path d="m22 12 4 6-4 1m24-5-4 6 4 1" fill="#EAB4A5" />
    <ellipse cx="34" cy="24" rx="16" ry="13" transform="rotate(12 34 24)" fill="#C48857" stroke="#704931" strokeWidth="2.2" />
    <ellipse cx="32" cy="29" rx="10" ry="7" transform="rotate(12 32 29)" fill="#F9E8CE" />
    <ellipse cx="27" cy="22" rx="2.6" ry="3.4" fill="#382B28" /><ellipse cx="41" cy="25" rx="2.6" ry="3.4" fill="#382B28" />
    <circle cx="27.7" cy="21" r="0.9" fill="white" /><circle cx="41.7" cy="24" r="0.9" fill="white" />
    <ellipse cx="23" cy="27" rx="3" ry="1.8" fill="#E99B8A" /><ellipse cx="44" cy="30" rx="3" ry="1.8" fill="#E99B8A" />
    <path d="m31 28 5 1-3 3Z" fill="#704931" stroke="#704931" strokeLinejoin="round" />
    <path d="M29 33q3 4 7 1" stroke="#704931" strokeWidth="1.5" strokeLinecap="round" />
    </g>
    {/* Nassau Hall's stone facade, central pediment and cupola. */}
    <path d="M18 53h112v33H18Z" fill="#C7AD87" stroke="#705C48" strokeWidth="1.5" />
    <path d="m13 53 8-7h107l8 7Z" fill="#61716A" stroke="#46574F" strokeWidth="1.5" />
    <path d="M62 50h25v36H62Z" fill="#DBC6A5" stroke="#705C48" strokeWidth="1.5" />
    <path d="m57 50 18-11 17 11Z" fill="#E6D6BB" stroke="#705C48" strokeWidth="1.5" />
    <path d="M69 31h12v11H69Z" fill="#E6D6BB" stroke="#705C48" strokeWidth="1.5" />
    <path d="M67 31q8-16 16 0Z" fill="#61716A" stroke="#46574F" strokeWidth="1.5" />
    <path d="M75 21v-7" stroke="#46574F" strokeWidth="1.5" />
    <path d="m75 14 11 3-11 3Z" fill="#ED8B23" />
    <path d="M72 34h6v6h-6Z" fill="#43515B" />
    {[27, 41, 99, 113].map((x) => <g key={x} fill="#43515B"><rect x={x} y="58" width="6" height="8" rx="0.6" /><rect x={x} y="72" width="6" height="8" rx="0.6" /></g>)}
    <path d="M69 86V73a6 6 0 0 1 12 0v13" fill="#594A3F" />
    <path d="M71 55h7v8h-7Z" fill="#43515B" />
    {/* Keep the label as real SVG text so it stays crisp at every size. */}
    <path d="M123 1h80a7 7 0 0 1 7 7v18a7 7 0 0 1-7 7h-67l-13 9 3-9h-3a7 7 0 0 1-7-7V8a7 7 0 0 1 7-7Z" fill="#FFF9EF" stroke="#704931" strokeWidth="1.5" strokeLinejoin="round" />
    <text x="163" y="21" textAnchor="middle" fill="#5D3823" fontFamily="Arial, sans-serif" fontSize="10" fontWeight="700">HackPrinceton</text>
    </svg>
  );
}
